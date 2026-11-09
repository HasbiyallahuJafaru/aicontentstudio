"""Disk space: what the studio's content takes, and wiping it. Everything generated lives under the media folder
(renders, clips, exports, downloaded footage, voice audio, motion layers) and in rows that hang off `projects` and
`assets` (ON DELETE CASCADE). Keys, settings and publishing credentials stay."""
import shutil

from app import config
from app.database import connect
from app.errors import UserError


def usage() -> dict:
    media = sum(f.stat().st_size for d in (config.MEDIA_DIR, config.DATA_DIR / "exports") if d.exists()
                for f in d.rglob("*") if f.is_file())
    with connect() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    return {"bytes": media, "projects": projects}


def clear() -> dict:
    """Delete every project, piece, render, clip, export and downloaded asset, files included."""
    with connect() as conn:
        if conn.execute("SELECT 1 FROM generation_jobs WHERE status IN ('queued', 'running')").fetchone():
            raise UserError("A job is still running. Wait for it to finish (or cancel it), then clear.")
        ids = [r[0] for r in conn.execute("SELECT id FROM projects")]
    from app.publish import posts
    for pid in ids:  # unschedule first: cleared content must not still go out
        posts.release(pid)
    with connect() as conn:
        conn.execute("DELETE FROM projects")  # cascades: pieces, jobs, renders, exports, clips, publications
        conn.execute("DELETE FROM assets")    # cascades: asset_usage
    freed = usage()["bytes"]
    shutil.rmtree(config.MEDIA_DIR, ignore_errors=True)
    shutil.rmtree(config.DATA_DIR / "exports", ignore_errors=True)  # exports live beside media, not in it
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("VACUUM")  # hand the deleted rows' pages back to the disk too
    return {"freed": freed}
