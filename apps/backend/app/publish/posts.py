"""Our record of where each clip is going: one publications row per clip per social account, with the state the
posting service last reported (scheduled | sending | sent | error | canceled). Also "Schedule all": many clips or
pieces at once, each at its own time (owner 2026-11-08: no approve step, no one-by-one posting). The service itself
is Zernio (zernio.py)."""
import json
from datetime import datetime, timedelta, timezone

from app.database import connect
from app.errors import UserError
from app.publish import zernio

LIVE = ('error', 'canceled')  # rows in these states don't hold a clip's slot on an account


def clip(project_id: str, idx: int) -> dict:
    """A postable clip with its per-network post copy: rendered and not rejected (there is no approve step)."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE project_id = ? AND idx = ?", (project_id, idx)).fetchone()
    if row is None:
        raise UserError("That clip doesn't exist any more. Re-clip the project.", f"clip {idx}")
    found = {**dict(row), "posts": json.loads(row["posts"])}
    if found["status"] == "rejected":
        raise UserError("This clip was rejected. Restore it before posting it.")
    if not found["video_path"]:
        raise UserError("This clip has no video yet. Clip the project again.")
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


def schedule(project_id: str, account_ids: list[str], items: list[dict]) -> list[dict]:
    """Schedules many posts at once on the same accounts, each at its own time. An item is {"clip_idx": n} or
    {"piece_id": id}, plus "due_at" (ISO with offset). Every time is checked before anything is sent; then each post
    goes out on its own, so one refusal (a video-only network for an image, say) never stops the others.
    Returns one result per item, in order: {"key", "ok", "error"?, "rows"?}."""
    if not items:
        raise UserError("Nothing to schedule. Every post here is already scheduled or posted.")
    zernio.check(account_ids)
    keys = []
    for item in items:
        key = f"piece:{item['piece_id']}" if item.get("piece_id") else f"clip:{item['clip_idx']}"
        try:
            zernio._when(item.get("due_at") or None)
        except UserError as e:
            n = "this piece" if item.get("piece_id") else f"clip {item['clip_idx']}"
            raise UserError(f"The time for {n} won't work: {e}", e.detail)
        keys.append(key)
    out = []
    for key, item in zip(keys, items):
        try:
            rows = (zernio.publish_piece(item["piece_id"], account_ids, item["due_at"]) if item.get("piece_id")
                    else zernio.publish(project_id, int(item["clip_idx"]), account_ids, item["due_at"]))
            failed = [r for r in rows if r["status"] == "error"]
            out.append({"key": key, "ok": not failed, "rows": rows,
                        **({"error": failed[0]["error"]} if failed else {})})
        except UserError as e:
            out.append({"key": key, "ok": False, "error": str(e)})
    return out


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
