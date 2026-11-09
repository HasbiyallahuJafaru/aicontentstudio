"""Zernio (https://docs.zernio.com), the hosted posting service: we send the finished clip and a time, Zernio posts
it to TikTok, Instagram, YouTube, Facebook, LinkedIn or X at that time, even with this computer switched off.

Why it is the simple path: Zernio holds the approved developer apps for every network and hosts the media itself
(POST /v1/media/presign, then a PUT), so the user needs no developer app and no storage bucket of their own. Setup
is a free Zernio account and one pasted API key; social accounts are then connected from inside our app, each one
a browser sign-in through Zernio's connect page.

The key lives in the DPAPI store (store.py), never in the renderer after it is handed over once.
# ponytail: one Zernio post per account (not one post fanned out), so unscheduling one network never touches the
# others; the video is still uploaded only once per publish.
# ponytail: the whole clip is read into memory for the upload (clips are tens of MB); stream it if renders grow."""
import os
import ssl
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app import config
from app.database import connect
from app.errors import UserError
from app.publish import store

API = os.environ.get("ACS_ZERNIO_URL", "https://zernio.com/api")  # env: tests/fakes
SIGNUP = "https://zernio.com/signup"
KEYS_PAGE = "https://zernio.com/dashboard/api-keys"
PROFILE_NAME = "AI Content Studio"
# Zernio's network name -> which of the clip's written posts it gets, and how we name it to people
NETWORKS = {"tiktok": "tiktok", "instagram": "instagram", "youtube": "youtube", "facebook": "facebook",
            "linkedin": "linkedin", "twitter": "x"}
LABELS = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube", "facebook": "Facebook",
          "linkedin": "LinkedIn", "twitter": "X"}
POST_LEAD = timedelta(minutes=2)  # "post now" = a couple of minutes out, so Zernio's scheduler does the work
RECONNECT = "Zernio didn't accept the saved key. Paste a new one in Settings, Posting."
# Zernio's per-network state -> ours (scheduled | sending | sent | error | canceled)
STATES = {"pending": "scheduled", "processing": "sending", "uploading": "sending", "published": "sent",
          "failed": "error", "cancelled": "canceled"}


def _request(method: str, path: str, key: str | None = None, **kw) -> dict:
    key = key or _key()
    try:
        r = httpx.request(method, f"{API}{path}", timeout=60, verify=ssl.create_default_context(),
                          headers={"Authorization": f"Bearer {key}"} | kw.pop("headers", {}), **kw)
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach Zernio. Check your internet connection and try again.", repr(e)) from e
    if r.status_code == 401:
        raise UserError(RECONNECT, r.text[:300])
    if r.status_code == 402 or (r.status_code == 403 and "plan" in r.text.lower()):
        raise UserError("Your Zernio plan's limit is reached for now. Check your plan at zernio.com.", r.text[:300])
    if r.status_code == 429:
        raise UserError("Zernio is busy with too many requests. Try again in a minute.", r.text[:300])
    if not r.is_success:
        try:
            reason = r.json().get("error") or ""
        except ValueError:
            reason = ""
        raise UserError(f"Zernio: {reason}" if reason else f"Zernio had a problem ({r.status_code}). Try again in a minute.",
                        f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def _key() -> str:
    saved = store.load("zernio")
    if not saved:
        raise UserError("Zernio isn't set up yet. Add your Zernio key in Settings, Posting.")
    return saved["api_key"]


# --- setup ------------------------------------------------------------------------------------------------------
def connection() -> dict:
    return {"connected": store.load("zernio") is not None, "signup_url": SIGNUP, "keys_url": KEYS_PAGE}


def save_key(api_key: str) -> dict:
    """Checks the key against Zernio before keeping it, so a typo is caught here rather than at posting time."""
    api_key = (api_key or "").strip()
    if not api_key.startswith("sk_"):
        raise UserError("That doesn't look like a Zernio API key. It starts with sk_. Copy it again from Zernio.")
    try:
        _request("GET", "/v1/accounts", key=api_key)
    except UserError as e:
        if e.args and e.args[0] == RECONNECT:
            raise UserError("Zernio didn't accept that key. Copy it again from your Zernio API keys page.") from e
        raise
    store.save("zernio", {"api_key": api_key})
    return connection()


def disconnect() -> None:
    store.delete("zernio")


def _profile_id() -> str:
    """Accounts are connected into a Zernio profile; use the first one, or make ours on first use."""
    saved = store.load("zernio") or {}
    if saved.get("profile_id"):
        return saved["profile_id"]
    profiles = _request("GET", "/v1/profiles").get("profiles") or []
    pid = profiles[0]["_id"] if profiles else _request("POST", "/v1/profiles", json={"name": PROFILE_NAME})["profile"]["_id"]
    store.save("zernio", saved | {"profile_id": pid})
    return pid


def connect_url(platform: str) -> str:
    """Zernio's sign-in page for one network, to open in the browser. The account shows up in accounts() once
    the person approves there."""
    if platform not in NETWORKS:
        raise UserError("That network can't be connected from here.")
    return _request("GET", f"/v1/connect/{platform}", params={"profileId": _profile_id()})["authUrl"]


def accounts() -> list[dict]:
    """The social accounts connected in Zernio that we write posts for."""
    found = _request("GET", "/v1/accounts").get("accounts") or []
    return [{"id": a["_id"], "platform": a["platform"], "label": LABELS[a["platform"]],
             "name": a.get("displayName") or a.get("username") or LABELS[a["platform"]],
             "username": a.get("username") or "", "picture": a.get("profilePicture"),
             "needs_reconnect": bool(a.get("needsReconnection")) or a.get("isActive") is False}
            for a in found if a.get("platform") in NETWORKS]


# --- publishing a clip or a piece ------------------------------------------------------------------------------
TYPES = {".mp4": ("video/mp4", "video"), ".jpg": ("image/jpeg", "image"), ".jpeg": ("image/jpeg", "image"),
         ".png": ("image/png", "image")}
VIDEO_ONLY = {"youtube"}  # networks that can't take a still image


def _upload(path) -> tuple[str, str]:
    """Puts a render in Zernio's own storage. Returns its public link and the media type posts declare."""
    content_type, media = TYPES.get(path.suffix.lower(), ("video/mp4", "video"))
    data = path.read_bytes()
    slot = _request("POST", "/v1/media/presign", json={"filename": path.name, "contentType": content_type, "size": len(data)})
    try:
        r = httpx.put(slot["uploadUrl"], content=data, headers={"Content-Type": content_type}, timeout=600,
                      verify=ssl.create_default_context())
    except httpx.HTTPError as e:
        raise UserError("The upload to Zernio stopped. Check your connection and try again.", repr(e)) from e
    if not r.is_success:
        raise UserError("Zernio's storage refused the upload. Try again in a minute.", f"HTTP {r.status_code}")
    return slot["publicUrl"], media


def _tiktok_privacy(account_id: str) -> str:
    """TikTok only takes a privacy level its creator-info lists for that account; public when it is offered."""
    found = _request("GET", f"/v1/accounts/{account_id}/tiktok/creator-info").get("privacyLevels") or []
    levels = [lv["value"] if isinstance(lv, dict) else lv for lv in found]  # live API: [{value, label}]
    return "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in levels or not levels else levels[0]


def _platform_data(title: str, account: dict, media: str) -> dict:
    platform, video = account["platform"], media == "video"
    if platform == "youtube":  # a title is required (100 characters at most); a short video becomes a Short
        return {"title": title[:100], "visibility": "public", "madeForKids": False}
    if platform == "tiktok":  # the person previewed it and pressed post: TikTok's consent fields
        return {"privacyLevel": _tiktok_privacy(account["id"]), "allowComment": True, "allowDuet": video,
                "allowStitch": video, "contentPreviewConfirmed": True, "expressConsentGiven": True} | (
            {"videoCoverTimestampMs": 1000} if video else {"mediaType": "photo"})
    if platform == "instagram" and video:
        return {"shareToFeed": True, "thumbOffset": 1000}
    if platform == "facebook" and video:
        return {"contentType": "reel", "title": title[:100]}
    return {}


def _when(due_at: str | None) -> datetime:
    now = datetime.now(timezone.utc)
    try:
        when = datetime.fromisoformat(due_at) if due_at else now + POST_LEAD
    except ValueError:
        when = None
    if when is None or when.tzinfo is None:
        raise UserError("That time couldn't be read. Pick it again.", due_at or "")
    if when < now:
        raise UserError("That time has already passed. Pick a time in the future.")
    return when


def check(account_ids: list[str]) -> list[dict]:
    """The chosen accounts, each still connected in Zernio."""
    if not account_ids:
        raise UserError("Choose at least one account to post to.")
    by_id = {a["id"]: a for a in accounts()}
    chosen = [by_id.get(i) for i in dict.fromkeys(account_ids)]
    if not all(chosen):
        raise UserError("One of those accounts isn't connected in Zernio any more. Reload and choose again.")
    if stale := [a["name"] for a in chosen if a["needs_reconnect"]]:
        raise UserError(f"Zernio needs you to sign in to {', '.join(stale)} again. Use Reconnect in Settings, Posting.")
    return chosen


def _send(project_id: str, idx: int, chosen: list[dict], path, texts: dict[str, str], title: str,
          when: datetime, piece_id: str | None = None) -> list[dict]:
    """Uploads the render once, then one Zernio post per account with that network's text. Returns one
    publication per account, including any Zernio refused."""
    from app.publish import posts  # our publications table (posts imports this module)

    url, media = _upload(path)
    rows = []
    for account in chosen:
        pub_id = uuid.uuid4().hex[:12]
        channel = {"id": f"zernio:{account['id']}", "service": NETWORKS[account["platform"]],
                   "displayName": f"{account['label']} · {account['name']}"}
        body = {"content": texts[account["platform"]], "mediaItems": [{"url": url, "type": media}],
                "platforms": [{"platform": account["platform"], "accountId": account["id"],
                               "platformSpecificData": _platform_data(title, account, media)}],
                "scheduledFor": when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
        try:
            post = _request("POST", "/v1/posts", json=body, headers={"Idempotency-Key": pub_id})["post"]
        except UserError as e:
            rows.append(posts.save(pub_id, project_id, idx, channel, when, error=str(e), piece_id=piece_id))
            if "Zernio: " not in str(e):  # key, plan or connection trouble: the other accounts would fail the same way
                raise
            continue
        rows.append(posts.save(pub_id, project_id, idx, channel, when, piece_id=piece_id, post={
            "id": post["_id"], "status": "scheduled", "dueAt": when.isoformat(), "sentAt": None,
            "externalLink": None, "error": None}))
    return rows


def publish(project_id: str, clip_idx: int, account_ids: list[str], due_at: str | None = None) -> list[dict]:
    """Schedules a clip on each chosen account with that network's own copy, now (in a couple of
    minutes) or at `due_at`."""
    from app.publish import posts

    when = _when(due_at)
    chosen = check(account_ids)
    clip = posts.clip(project_id, clip_idx)
    if taken := posts.taken(project_id, clip_idx, [f"zernio:{a['id']}" for a in chosen]):
        raise UserError(f"This clip is already scheduled or posted on {', '.join(taken)}. Unschedule it first.")
    texts = {a["platform"]: clip["posts"][NETWORKS[a["platform"]]] for a in chosen}
    return _send(project_id, clip_idx, chosen, config.MEDIA_DIR / clip["video_path"], texts, clip["title"], when)


def piece_texts(meta: dict) -> dict[str, str]:
    """Each network's post text from a piece's metadata, by the same rules as its export (platforms.py)."""
    from app.platforms import IG_CAPTION_MAX, tags

    caption, plain = meta["caption"], " ".join(tags(meta))
    x = f"{caption} {' '.join(tags(meta)[:2])}"
    return {"youtube": f'{meta["description"]}\n\n{" ".join(tags(meta, ("Shorts",)))}',
            "tiktok": f"{caption} {plain}"[:IG_CAPTION_MAX], "instagram": f"{caption}\n\n{plain}"[:IG_CAPTION_MAX],
            "facebook": f"{caption}\n\n{plain}", "linkedin": f"{caption}\n\n{plain}"[:3000],
            "twitter": x if len(x) <= 280 else caption[:279].rstrip() + "…"}


def publish_piece(piece_id: str, account_ids: list[str], due_at: str | None = None) -> list[dict]:
    """Posts a rendered quote image or narrated video: the video when the piece has one, else the image. Each
    network gets its caption and hashtags from the piece's metadata."""
    from app import content
    from app.export import EXPORTABLE
    from app.publish import posts

    piece = content._piece(piece_id)
    with connect() as conn:
        found = {r["kind"]: r["local_path"] for r in conn.execute(
            "SELECT kind, local_path FROM renders WHERE piece_id = ?", (piece_id,)).fetchall()}
    if piece["status"] not in EXPORTABLE or not found:
        raise UserError("Render this piece before posting it.")
    when = _when(due_at)
    chosen = check(account_ids)
    if "video" not in found and (video_only := [a["label"] for a in chosen if a["platform"] in VIDEO_ONLY]):
        raise UserError(f"{' and '.join(video_only)} only takes videos, and this piece is an image. Untick it and post again.")
    channel_ids = [f"zernio:{a['id']}" for a in chosen]
    if taken := posts.taken(piece["project_id"], piece["idx"], channel_ids, piece_id=piece_id):
        raise UserError(f"This piece is already scheduled or posted on {', '.join(taken)}. Unschedule it first.")
    meta = piece["content"]["metadata"]
    path = config.MEDIA_DIR / found.get("video", found.get("image"))
    return _send(piece["project_id"], piece["idx"], chosen, path, piece_texts(meta), meta["title"], when, piece_id)


def refresh(row: dict) -> dict | None:
    """Zernio's current view of one of our publications, in the shape posts.save takes. None: deleted there."""
    try:
        post = _request("GET", f"/v1/posts/{row['external_id']}")["post"]
    except UserError as e:
        if "not found" in str(e).lower() or "404" in (e.detail or ""):
            return None
        raise
    entry = next(iter(post.get("platforms") or []), {})
    status = STATES.get(entry.get("status"), "scheduled")
    return {"id": post["_id"], "status": status, "dueAt": entry.get("scheduledFor") or post.get("scheduledFor"),
            "sentAt": entry.get("publishedAt"), "externalLink": entry.get("platformPostUrl"),
            "error": {"message": entry.get("errorMessage")} if status == "error" else None}


def unschedule(external_id: str) -> None:
    try:
        _request("DELETE", f"/v1/posts/{external_id}")
    except UserError as e:
        if "not found" not in str(e).lower() and "404" not in (e.detail or ""):
            raise
