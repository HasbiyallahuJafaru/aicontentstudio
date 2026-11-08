"""Our record of where each clip is going: one publications row per clip per social account, with the state the
posting service last reported (scheduled | sending | sent | error | canceled). Also the posting calendar, which
spreads a project's approved clips over chosen days and times. The service itself is Zernio (zernio.py)."""
import json
from datetime import datetime, time, timedelta, timezone
from itertools import islice
from zoneinfo import ZoneInfo

from app.database import connect
from app.errors import UserError
from app.publish import zernio

AHEAD = timedelta(days=30)  # how far ahead the calendar plans
LIVE = ('error', 'canceled')  # rows in these states don't hold a clip's slot on an account


def clip(project_id: str, idx: int) -> dict:
    """An approved clip with its per-network post copy."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE project_id = ? AND idx = ?", (project_id, idx)).fetchone()
    if row is None:
        raise UserError("That clip doesn't exist any more. Re-clip the project.", f"clip {idx}")
    found = {**dict(row), "posts": json.loads(row["posts"])}
    if found["status"] != "approved":
        raise UserError("Approve this clip before publishing it.")
    return found


def taken(project_id: str, idx: int, channel_ids: list[str], piece_id: str | None = None) -> list[str]:
    """Names of the accounts this clip (or piece) is already scheduled or posted on."""
    which, key = ("piece_id = ?", piece_id) if piece_id else ("clip_idx = ? AND piece_id IS NULL", idx)
    with connect() as conn:
        rows = conn.execute(f"SELECT channel_name FROM publications WHERE project_id = ? AND {which} AND "
                            f"channel_id IN ({','.join('?' * len(channel_ids))}) AND status NOT IN (?, ?)",
                            (project_id, key, *channel_ids, *LIVE)).fetchall()
    return [r["channel_name"] for r in rows]


def save(pub_id: str, project_id: str, clip_idx: int, channel: dict, due_at: datetime | None,
         post: dict | None = None, error: str | None = None, piece_id: str | None = None) -> dict:
    """Records the service's view of a post, or why it failed."""
    if post is None:
        post = {"id": None, "status": "error", "dueAt": None, "sentAt": None, "externalLink": None,
                "error": {"message": error}}
    with connect() as conn:
        conn.execute("INSERT INTO publications (id, project_id, clip_idx, provider, channel_id, service, "
                     "channel_name, status, due_at, sent_at, external_id, external_link, error, piece_id, checked_at) "
                     "VALUES (?,?,?,'zernio',?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
                     "ON CONFLICT (id) DO UPDATE SET status = excluded.status, due_at = COALESCE(excluded.due_at, due_at), "
                     "sent_at = excluded.sent_at, external_id = COALESCE(excluded.external_id, external_id), "
                     "external_link = excluded.external_link, error = excluded.error, "
                     "checked_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
                     (pub_id, project_id, clip_idx, channel["id"], channel["service"],
                      channel.get("displayName") or channel["service"],
                      post["status"], _iso(post["dueAt"]), _iso(post["sentAt"]), post["id"],
                      post["externalLink"], error or (post.get("error") or {}).get("message"), piece_id))
    return _get(pub_id)


def _iso(value) -> str | None:
    if not value:
        return None
    return value if isinstance(value, str) else value.isoformat()


def _get(pub_id: str) -> dict:
    with connect() as conn:
        return dict(conn.execute("SELECT * FROM publications WHERE id = ?", (pub_id,)).fetchone())


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def slots(days: list[int], times: list[str], start, earliest: datetime, until: datetime, tz: str) -> list[datetime]:
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


def calendar(project_id: str, account_ids: list[str], days: list[int], times: list[str],
             start: str, tz: str, dry_run: bool = False) -> dict:
    """Spreads the project's approved, unscheduled clips over the calendar's posting times, up to 30 days ahead,
    scheduling each on the chosen Zernio accounts. `left`: clips that didn't fit. `dry_run`: only plan, so the
    person sees every slot before anything is sent."""
    now = datetime.now(timezone.utc)
    try:
        ZoneInfo(tz)
    except (KeyError, ValueError):
        raise UserError("That time zone isn't known. Use one like Europe/London or America/New_York.")
    if not days or not times:
        raise UserError("Pick at least one posting day and one time.")
    if not dry_run:
        zernio.check(account_ids)
    with connect() as conn:
        rows = conn.execute("SELECT * FROM clips WHERE project_id = ? AND status = 'approved' ORDER BY idx",
                            (project_id,)).fetchall()
        used = {r["clip_idx"] for r in conn.execute(
            "SELECT clip_idx FROM publications WHERE project_id = ? AND piece_id IS NULL AND status NOT IN (?, ?)",
            (project_id, *LIVE))}
        others = conn.execute("SELECT due_at FROM publications WHERE status NOT IN (?, ?)", LIVE).fetchall()
    busy = {r["due_at"] for r in others if _parse(r["due_at"]) and _parse(r["due_at"]) > now}
    clips = [dict(r) for r in rows if r["idx"] not in used]
    if not clips:
        raise UserError("Every approved clip is already scheduled or posted. Approve more clips first.")
    first_day = datetime.strptime(start, "%Y-%m-%d").date()
    free = (at for at in slots(days, times, first_day, now + timedelta(minutes=30), now + AHEAD, tz)
            if at.isoformat() not in busy)
    due = list(islice(free, len(clips)))
    if not due:
        raise UserError(f"None of those days and times fall within the next {AHEAD.days} days. Pick an earlier start.")
    if not dry_run:
        for c, at in zip(clips, due):
            zernio.publish(project_id, c["idx"], account_ids, at.isoformat())
    return {"scheduled": [{"clip_idx": c["idx"], "title": c["title"], "due_at": a.isoformat()} for c, a in zip(clips, due)],
            "left": [c["idx"] for c in clips[len(due):]]}


def publications(project_id: str) -> list[dict]:
    """The project's posts, asking Zernio again about any whose time has come (at most once a minute each; the
    last known state if Zernio can't be reached)."""
    now = datetime.now(timezone.utc)
    with connect() as conn:
        waiting = [dict(r) for r in conn.execute(
            "SELECT * FROM publications WHERE project_id = ? AND status NOT IN ('sent', 'error', 'canceled') "
            "AND external_id IS NOT NULL", (project_id,)).fetchall()]
    for row in waiting:
        due, checked = _parse(row["due_at"] or row["created_at"]), _parse(row["checked_at"])
        if not due or due > now or (checked and checked > now - timedelta(minutes=1)) or row["provider"] != "zernio":
            continue
        try:
            fresh = zernio.refresh(row)
        except UserError:
            continue  # last known state; try again on the next list
        if fresh is None:  # deleted inside Zernio
            with connect() as conn:
                conn.execute("DELETE FROM publications WHERE id = ?", (row["id"],))
            continue
        save(row["id"], project_id, row["clip_idx"], {"id": row["channel_id"], "service": row["service"],
             "displayName": row["channel_name"]}, None, post=fresh)
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM publications WHERE project_id = ? ORDER BY clip_idx, "
                                              "created_at", (project_id,)).fetchall()]


def remove(publication_id: str) -> dict:
    """Unschedules a post (deletes it in Zernio) or clears a failed attempt."""
    row = _get(publication_id)
    if row["status"] == "sent":
        raise UserError("This post has already gone out. Delete it on the network itself.")
    if row["provider"] == "zernio" and row["external_id"] and row["status"] not in LIVE:
        zernio.unschedule(row["external_id"])
    with connect() as conn:
        conn.execute("DELETE FROM publications WHERE id = ?", (publication_id,))
    return {"removed": publication_id}
