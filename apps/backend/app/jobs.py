"""Lightweight local job manager (PRD §38). One thread per job; state in SQLite; progress pushed as events.

kind = 'generate' writes content (M2), kind = 'render' produces videos/images (M5); both share this runner.
"""
import json
import logging
import threading
import uuid

from app import content, export, renders
from app.database import connect
from app.errors import UserError
from app.events import emit

log = logging.getLogger("jobs")
_cancelled: set[str] = set()


class Cancelled(Exception):
    pass


def _row(r) -> dict:
    return {**dict(r), "error": json.loads(r["error"]) if r["error"] else None}


def get(id: str) -> dict:
    with connect() as conn:
        r = conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (id,)).fetchone()
    return _row(r)


def latest(project_id: str) -> dict | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM generation_jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                         (project_id,)).fetchone()
    return _row(r) if r else None


def _set(job_id: str, event: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE generation_jobs SET {cols}, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                     (*fields.values(), job_id))
    emit(event, get(job_id))


def _project_status(project_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE projects SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                     (status, project_id))


def start(project_id: str, kind: str = "generate", piece_ids: list[str] | None = None) -> dict:
    if kind not in ("generate", "render", "export"):
        raise UserError("Unknown job kind.", kind)
    running = latest(project_id)
    if running and running["status"] in ("queued", "running"):
        raise UserError("This project already has a job running.")
    job_id = uuid.uuid4().hex[:12]
    with connect() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            raise UserError("This project no longer exists.", f"project id {project_id}")
        conn.execute("INSERT INTO generation_jobs (id, project_id, kind) VALUES (?, ?, ?)", (job_id, project_id, kind))
    if kind == "generate":  # render/export ride the same job system but don't change the project's own stage
        _project_status(project_id, "generating")
    threading.Thread(target=_run, args=(job_id, project_id, kind, piece_ids), daemon=True,
                     name=f"job-{job_id}").start()
    return get(job_id)


def cancel(id: str) -> dict:
    _cancelled.add(id)  # checked between pipeline steps; an in-flight API call finishes first
    return {"cancelling": id}


def _run(job_id: str, project_id: str, kind: str = "generate", piece_ids: list[str] | None = None) -> None:
    def report(stage: str, progress: float) -> None:
        if job_id in _cancelled:
            raise Cancelled
        _set(job_id, "job.progress", stage=stage, progress=round(progress, 3))

    stage = {"generate": "Generating", "render": "Rendering", "export": "Exporting"}[kind]
    _set(job_id, "job.started", status="running", stage=stage)
    try:
        if kind == "export":
            export.export_project(project_id, report, piece_ids)
        else:
            (content.generate if kind == "generate" else renders.render_project)(project_id, report)
    except Cancelled:
        _project_status(project_id, "draft" if not content.pieces(project_id) else "ready")
        _set(job_id, "job.cancelled", status="cancelled", stage="Cancelled")
    except UserError as e:
        _project_status(project_id, "failed")
        _set(job_id, "job.failed", status="failed", error=json.dumps({"message": str(e), "detail": e.detail}))
    except Exception as e:
        log.exception("job %s failed", job_id)
        _project_status(project_id, "failed")
        _set(job_id, "job.failed", status="failed",
             error=json.dumps({"message": "Generation failed unexpectedly.", "detail": repr(e)}))
    else:
        _project_status(project_id, "ready")
        _set(job_id, "job.completed", status="completed", stage="Done", progress=1.0)
    finally:
        _cancelled.discard(job_id)


def recover() -> None:
    """On startup: jobs that were running when the app closed can't resume; mark them failed, honestly."""
    err = json.dumps({"message": "Generation stopped because the app closed. Generate again to retry.", "detail": ""})
    with connect() as conn:
        conn.execute("UPDATE generation_jobs SET status = 'failed', error = ? WHERE status IN ('queued','running')", (err,))
        conn.execute("UPDATE projects SET status = CASE WHEN EXISTS (SELECT 1 FROM content_pieces c WHERE c.project_id = "
                     "projects.id) THEN 'ready' ELSE 'failed' END WHERE status = 'generating'")
