"""Buffer publishing (https://developers.buffer.com), ported from ClipperAi and cut down for one local user:
no owners or workspace keys (the connected account is the only identity), no local queue or worker (Buffer
holds scheduled posts itself — we create them directly), and a 30-day scheduling horizon.
# ponytail: creating a month of posts in one go can hit Buffer's request limit; the human error from the API
# says so, and the already-created posts are listed and removable."""
import json
import os
import uuid
from datetime import datetime, time, timedelta, timezone
from itertools import islice
from zoneinfo import ZoneInfo

import httpx
import ssl

from app import config
from app.database import connect
from app.errors import UserError
from app.publish import host
from app.publish import oauth

API = os.environ.get("ACS_BUFFER_URL", "https://api.buffer.com")  # env: tests/fakes
# Buffer's name for a network -> which of the clip's written posts it gets
SERVICES = {"tiktok": "tiktok", "instagram": "instagram", "youtube": "youtube", "linkedin": "linkedin",
            "facebook": "facebook", "twitter": "x"}
AHEAD = timedelta(days=30)
CREATE = """mutation($input: CreatePostInput!) { createPost(input: $input) {
    ... on PostActionSuccess { post { id status dueAt sentAt externalLink error { message } } }
    ... on MutationError { message } } }"""
POST = "query($id: PostId!) { post(input: {id: $id}) { id status dueAt sentAt externalLink error { message } } }"
DELETE = """mutation($id: PostId!) { deletePost(input: {id: $id}) {
    ... on DeletePostSuccess { id } ... on MutationError { message } } }"""


def call(query: str, **variables) -> dict:
    """One GraphQL request with the connected account's token. Raises UserError with a readable reason for
    anything but data."""
    request = httpx.Request("POST", API, json={"query": query, "variables": variables},
                            headers={"Content-Type": "application/json",
                                     "Authorization": f"Bearer {oauth.token()}"})
    try:
        with httpx.Client(verify=ssl.create_default_context(), timeout=30) as client:
            r = client.send(request)
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach Buffer. Try again in a minute.", repr(e)) from e
    if r.status_code == 401:
        raise UserError("Buffer disconnected your account. Connect it again in Settings, Publishing.")
    if r.status_code == 429:
        minutes = -(-int(r.headers.get("Retry-After") or 60) // 60)
        raise UserError(f"Buffer's request limit is used up for now. Try again in {minutes} minute"
                        f"{'s' if minutes != 1 else ''}.")
    if not r.is_success:
        raise UserError(f"Buffer had a problem ({r.status_code}). Try again in a minute.", r.text[:300])
    body = r.json()
    if errors := body.get("errors"):
        raise UserError(f"Buffer: {errors[0]['message']}", json.dumps(errors[0]))
    return body["data"]


def channels() -> list[dict]:
    """The social accounts connected in Buffer. `usable`: a network we write copy for, connected, not locked
    by Buffer's plan, and not a personal Instagram profile (Buffer only sends those a post-by-hand reminder)."""
    found = []
    for organization in call("{ account { organizations { id } } }")["account"]["organizations"]:
        found += call("""query($id: OrganizationId!) { channels(input: {organizationId: $id}) {
                             id service type name displayName isDisconnected isLocked } }""",
                      id=organization["id"])["channels"]
    return [c | {"usable": c["service"] in SERVICES and not c["isDisconnected"] and not c["isLocked"]
                 and not (c["service"] == "instagram" and c["type"] == "profile")} for c in found]


def _ready(channel_ids: list[str]) -> list[dict]:
    if not host.configured():
        raise UserError("Publishing needs somewhere public to host the video. Add an S3-compatible bucket "
                        "(Cloudflare R2 works) under Settings, Publishing.")
    by_id = {c["id"]: c for c in channels()}
    chosen = [by_id.get(i) for i in dict.fromkeys(channel_ids)]
    if not all(c and c["usable"] for c in chosen):
        raise UserError("One of those channels can't be used any more. Reload and choose again.")
    return chosen


def post_input(clip: dict, channel: dict, video_url: str, due_at: datetime | None) -> dict:
    service = channel["service"]
    # YouTube requires a title (100 characters at most) and a category
    # ponytail: every clip is "People & Blogs" (22, YouTube's upload default); let the copywriter pick one if it matters
    metadata = {"youtube": {"title": clip["title"][:100], "categoryId": "22"},
                "instagram": {"type": "reel", "shouldShareToFeed": True}, "facebook": {"type": "reel"}}.get(service)
    video = {"url": video_url}
    if service in ("instagram", "tiktok"):  # the only networks that take a cover frame; ours is the frame at 1 s
        video["metadata"] = {"thumbnailOffset": 1000}
    return {"channelId": channel["id"], "text": clip["posts"][SERVICES[service]], "assets": [{"video": video}],
            "schedulingType": "automatic", "needsApproval": False,
            "mode": "customScheduled" if due_at else "shareNow", "dueAt": due_at and due_at.isoformat()} | (
        {"metadata": {service: metadata}} if metadata else {})


def _clip(project_id: str, idx: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE project_id = ? AND idx = ?", (project_id, idx)).fetchone()
    if row is None:
        raise UserError("That clip doesn't exist any more. Re-clip the project.", f"clip {idx}")
    clip = {**dict(row), "posts": json.loads(row["posts"])}
    if clip["status"] != "approved":
        raise UserError("Approve this clip before publishing it.")
    return clip


def _taken(project_id: str, idx: int, channel_ids: list[str]) -> list[str]:
    with connect() as conn:
        rows = conn.execute(f"SELECT channel_name FROM publications WHERE project_id = ? AND clip_idx = ? AND "
                            f"channel_id IN ({','.join('?' * len(channel_ids))}) AND status <> 'error'",
                            (project_id, idx, *channel_ids)).fetchall()
    return [r["channel_name"] for r in rows]


def publish(project_id: str, clip_idx: int, channel_ids: list[str], due_at: str | None = None) -> list[dict]:
    """Sends an approved clip to Buffer channels, now or at `due_at` (ISO). Returns one publication per
    channel, including any Buffer refused (status "error" with its reason)."""
    if not channel_ids:
        raise UserError("Choose at least one channel to publish to.")
    when = _parse(due_at) if due_at else None
    if due_at and when is None:
        raise UserError("That time couldn't be read. Use an ISO time like 2026-09-21T09:00:00+01:00.")
    now = datetime.now(timezone.utc)
    if when and when < now:
        raise UserError("That time has already passed. Pick a time in the future.")
    if when and when > now + AHEAD:
        raise UserError(f"Posts can be scheduled up to {AHEAD.days} days ahead. Pick an earlier time.")
    chosen = _ready(channel_ids)
    clip = _clip(project_id, clip_idx)
    if taken := _taken(project_id, clip_idx, channel_ids):
        raise UserError(f"This clip is already scheduled or posted on {', '.join(taken)}. Unschedule it first.")
    published = []
    for channel in chosen:
        pub_id = uuid.uuid4().hex[:12]
        try:
            video_url = host.upload(config.MEDIA_DIR / clip["video_path"], f"{pub_id}.mp4")
            result = call(CREATE, input=post_input(clip, channel, video_url, when))["createPost"]
        except UserError as e:  # key, limit or connection trouble: the remaining channels would fail the same way
            _save(pub_id, project_id, clip_idx, channel, when, error=str(e))
            raise
        row = _save(pub_id, project_id, clip_idx, channel, when,
                    post=result["post"] if "post" in result else None,
                    error=result["message"] if "post" not in result else None)
        published.append(row)
    return published


def _save(pub_id: str, project_id: str, clip_idx: int, channel: dict, due_at: datetime | None,
          post: dict | None = None, error: str | None = None) -> dict:
    """Records Buffer's view of a post, or why it failed."""
    if post is None:
        post = {"id": None, "status": "error", "dueAt": None, "sentAt": None, "externalLink": None,
                "error": {"message": error}}
    with connect() as conn:
        conn.execute("INSERT INTO publications (id, project_id, clip_idx, provider, channel_id, service, "
                     "channel_name, status, due_at, sent_at, external_id, external_link, error, checked_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
                     "ON CONFLICT (id) DO UPDATE SET status = excluded.status, due_at = COALESCE(excluded.due_at, due_at), "
                     "sent_at = excluded.sent_at, external_id = COALESCE(excluded.external_id, external_id), "
                     "external_link = excluded.external_link, error = excluded.error, "
                     "checked_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
                     (pub_id, project_id, clip_idx, "buffer", channel["id"], channel["service"],
                      channel.get("displayName") or channel.get("name") or channel["service"],
                      post["status"], _iso(post["dueAt"]), _iso(post["sentAt"]), post["id"],
                      post["externalLink"], error or (post.get("error") or {}).get("message")))
    return _get(pub_id)


def _iso(value) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _get(pub_id: str) -> dict:
    with connect() as conn:
        return dict(conn.execute("SELECT * FROM publications WHERE id = ?", (pub_id,)).fetchone())


def slots(days: list[int], times: list[str], start, earliest: datetime, until: datetime, tz: str) -> list[dict]:
    """The calendar's posting times in order: each chosen time on each chosen weekday from `start`, in the
    calendar's time zone (so daylight saving is followed), that falls between `earliest` and `until`."""
    zone = ZoneInfo(tz)
    parsed = [datetime.strptime(t, "%H:%M").time() for t in times]
    day = max(start, earliest.astimezone(zone).date())
    found = []
    while datetime.combine(day, time.min, zone) <= until:
        if day.isoweekday() in days:
            for at in sorted(datetime.combine(day, t, zone) for t in set(parsed)):
                if earliest <= at <= until:
                    found.append(at.astimezone(timezone.utc))
        day += timedelta(days=1)
    return found


def calendar(project_id: str, channel_ids: list[str], days: list[int], times: list[str],
             start: str, tz: str) -> dict:
    """Spreads the project's approved, unpublished clips over the calendar's posting times, up to 30 days
    ahead, creating each Buffer post directly. `left`: clips that didn't fit."""
    now = datetime.now(timezone.utc)
    try:
        zone = ZoneInfo(tz)
    except (KeyError, ValueError):
        raise UserError("That time zone isn't known. Use one like Europe/London or America/New_York.")
    chosen = _ready(channel_ids)
    with connect() as conn:
        rows = conn.execute("SELECT * FROM clips WHERE project_id = ? AND status = 'approved' ORDER BY idx",
                            (project_id,)).fetchall()
        taken = {r["clip_idx"] for r in conn.execute(
            "SELECT clip_idx FROM publications WHERE project_id = ? AND status <> 'error'", (project_id,)).fetchall()}
        others = conn.execute("SELECT due_at FROM publications WHERE status <> 'error'", ()).fetchall()
    busy = {r["due_at"] for r in others
            if r["due_at"] and _parse(r["due_at"]) and _parse(r["due_at"]) > now}
    clips = [dict(r) for r in rows if r["idx"] not in taken]
    if not clips:
        raise UserError("Every approved clip is already scheduled or posted. Approve more clips first.")
    first_day = datetime.strptime(start, "%Y-%m-%d").date()
    free = (at for at in slots(days, times, first_day, now + timedelta(minutes=30), now + AHEAD, tz)
            if at.isoformat() not in busy)
    due = list(islice(free, len(clips)))
    if not due:
        raise UserError(f"None of those days and times fall within the next {AHEAD.days} days. Pick an earlier start.")
    for clip, at in zip(clips, due):
        publish(project_id, clip["idx"], channel_ids, at)
    return {"scheduled": [{"clip_idx": c["idx"], "title": c["title"], "due_at": a.isoformat()}
                          for c, a in zip(clips, due)],
            "left": [c["idx"] for c in clips[len(due):]]}


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def publications(project_id: str) -> list[dict]:
    """The project's posts, refreshing Buffer's view of any post whose time has come (at most once a minute
    each; last known state if Buffer can't be reached)."""
    with connect() as conn:
        due = [dict(r) for r in conn.execute(
            "SELECT * FROM publications WHERE project_id = ? AND provider = 'buffer' AND "
            "status NOT IN ('sent', 'error') AND external_id IS NOT NULL", (project_id,)).fetchall()]
    now = datetime.now(timezone.utc)
    due = [r for r in due
           if _parse(r["due_at"] or r["created_at"]) and _parse(r["due_at"] or r["created_at"]) <= now
           and (_parse(r["checked_at"]) is None or _parse(r["checked_at"]) < now - timedelta(minutes=1))]
    for row in due:
        try:
            fresh = call(POST, id=row["external_id"])["post"]
        except UserError as e:
            if "not found" not in str(e).lower():
                continue  # last known state is better than nothing; try again on the next list
            with connect() as conn:  # deleted inside Buffer
                conn.execute("DELETE FROM publications WHERE id = ?", (row["id"],))
            continue
        channel = {"id": row["channel_id"], "service": row["service"],
                   "displayName": row["channel_name"]}
        _save(row["id"], project_id, row["clip_idx"], channel, None, post=fresh)
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM publications WHERE project_id = ? ORDER BY clip_idx, "
                                              "created_at", (project_id,)).fetchall()]


def remove(publication_id: str) -> dict:
    """Unschedules a post (deletes it from Buffer) or clears a failed attempt."""
    row = _get(publication_id)
    if row["status"] == "sent":
        raise UserError("This post has already gone out. Delete it on the network itself.")
    if row["external_id"] and row["status"] != "error":
        result = call(DELETE, id=row["external_id"])["deletePost"]
        if "message" in result and "not found" not in result["message"].lower():  # not found: already gone
            raise UserError(f"Buffer: {result['message']}")
    with connect() as conn:
        conn.execute("DELETE FROM publications WHERE id = ?", (publication_id,))
    return {"removed": publication_id}
