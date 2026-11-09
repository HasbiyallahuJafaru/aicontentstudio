"""Lightweight local job manager (PRD §38). One thread per job; state in SQLite; progress pushed as events.

kind = 'generate' writes content (M2), kind = 'render' produces videos/images (M5); both share this runner.
"""
import json
import logging
import threading
import time
import uuid

from app import assets, clips, content, export, renders
from app.database import connect
from app.errors import Cancelled, UserError, explain
from app.events import emit

log = logging.getLogger("jobs")
_cancelled: set[str] = set()


def _row(r) -> dict:
    return {**dict(r), "error": json.loads(r["error"]) if r["error"] else None,
            "log": json.loads(r["log"]) if r["log"] else []}


LOG_CAP = 400  # ponytail: a 100-piece render logs ~500 steps; keep the newest 400


class StepLog:
    """Each new stage text starts a step; the previous one closes as done with its duration. A pipeline marks the
    current step failed (and keeps going) with fail(); the runner closes the last step when the job ends."""

    def __init__(self):
        self.steps: list[dict] = []
        self._t = 0.0

    def stage(self, text: str) -> None:
        if self.steps and self.steps[-1]["step"] == text:
            return
        self.close("done")
        self._t = time.monotonic()
        self.steps.append({"step": text, "status": "running", "secs": 0})
        del self.steps[:-LOG_CAP]

    def close(self, status: str, error: str | None = None, detail: str | None = None) -> None:
        if not self.steps or self.steps[-1]["status"] != "running":
            return
        last = self.steps[-1]
        last.update(status=status, secs=round(time.monotonic() - self._t, 1))
        if error:
            last["error"] = error
        if detail:
            last["detail"] = detail[-1500:]

    def json(self) -> str:
        return json.dumps(self.steps, ensure_ascii=False)


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
    if kind not in ("generate", "render", "export", "clip", "visuals", "visuals_render"):
        raise UserError("Unknown job kind.", kind)
    running = latest(project_id)
    if running and running["status"] in ("queued", "running"):
        raise UserError("This project already has a job running.")
    job_id = uuid.uuid4().hex[:12]
    with connect() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            raise UserError("This project no longer exists.", f"project id {project_id}")
        conn.execute("INSERT INTO generation_jobs (id, project_id, kind) VALUES (?, ?, ?)", (job_id, project_id, kind))
    if kind in ("generate", "clip"):  # render/export ride the same job system but don't change the project's own stage
        _project_status(project_id, "generating")
    threading.Thread(target=_run, args=(job_id, project_id, kind, piece_ids), daemon=True,
                     name=f"job-{job_id}").start()
    return get(job_id)


def ensure_idle(project_id: str) -> None:
    """Refuse a delete while a job works on the project: ffmpeg may be reading the very files."""
    running = latest(project_id)
    if running and running["status"] in ("queued", "running"):
        raise UserError("This project has a job running. Wait for it to finish (or cancel it) before deleting.")


def cancel(id: str) -> dict:
    _cancelled.add(id)  # checked between pipeline steps; an in-flight API call finishes first
    return {"cancelling": id}


def _run(job_id: str, project_id: str, kind: str = "generate", piece_ids: list[str] | None = None) -> None:
    steps = StepLog()

    def report(stage: str, progress: float) -> None:
        if job_id in _cancelled:
            raise Cancelled
        steps.stage(stage)
        _set(job_id, "job.progress", stage=stage, progress=round(progress, 3), log=steps.json())

    def fail(error: str, detail: str | None = None) -> None:
        """A pipeline hit a failure it survives (one piece of many): mark the step, keep the job going."""
        steps.close("failed", error, detail)
        _set(job_id, "job.progress", log=steps.json())

    report.fail = fail  # ponytail: an attribute, so the dozen report(stage, p) call sites stay as they are

    stage = {"generate": "Generating", "render": "Rendering", "export": "Exporting", "clip": "Clipping",
             "visuals": "Downloading footage", "visuals_render": "Downloading footage"}[kind]
    steps.stage(stage)
    _set(job_id, "job.started", status="running", stage=stage, log=steps.json())
    try:
        if kind == "export":
            export.export_project(project_id, report, piece_ids)
        elif kind == "clip":
            clips.run(project_id, report)
        elif kind == "visuals":
            assets.download_picks(project_id, report)
        elif kind == "visuals_render":  # "Download and render": the picked footage, then every piece, one progress bar
            assets.download_picks(project_id, _scaled(report, 0, 0.3))
            renders.render_project(project_id, _scaled(report, 0.3, 0.7), piece_ids)
        elif kind == "render":
            renders.render_project(project_id, report, piece_ids)
        else:
            content.generate(project_id, report)
    except Cancelled:
        steps.close("cancelled")
        _project_status(project_id, _settled_status(project_id))
        _set(job_id, "job.cancelled", status="cancelled", stage="Cancelled", log=steps.json())
    except UserError as e:
        steps.close("failed", str(e), e.detail)
        _project_status(project_id, "failed")
        _set(job_id, "job.failed", status="failed", error=json.dumps({"message": str(e), "detail": e.detail}),
             log=steps.json())
    except Exception as e:
        log.exception("job %s failed", job_id)
        message, detail = explain(e)
        steps.close("failed", message, detail)
        _project_status(project_id, "failed")
        _set(job_id, "job.failed", status="failed", error=json.dumps({"message": message, "detail": detail}),
             log=steps.json())
    else:
        steps.close("done")
        failed = sum(s["status"] == "failed" for s in steps.steps)
        _project_status(project_id, "ready")
        _set(job_id, "job.completed", status="completed", progress=1.0, log=steps.json(),
             stage=f"Done, {failed} failed" if failed else "Done")
    finally:
        _cancelled.discard(job_id)


def _scaled(report, start: float, span: float):
    """A report for one leg of a multi-leg job: its 0..1 maps onto start..start+span of the job's bar."""
    def leg(stage: str, progress: float) -> None:
        report(stage, start + progress * span)
    leg.fail = report.fail
    return leg


def _settled_status(project_id: str) -> str:
    """After a cancel: 'ready' when anything usable exists, else back to 'draft'."""
    with connect() as conn:
        has = (conn.execute("SELECT 1 FROM content_pieces WHERE project_id = ? LIMIT 1", (project_id,)).fetchone()
               or conn.execute("SELECT 1 FROM clips WHERE project_id = ? LIMIT 1", (project_id,)).fetchone())
    return "ready" if has else "draft"


def recover() -> None:
    """On startup: jobs that were running when the app closed can't resume; mark them failed, honestly."""
    err = json.dumps({"message": "Generation stopped because the app closed. Generate again to retry.", "detail": ""})
    with connect() as conn:
        conn.execute("UPDATE generation_jobs SET status = 'failed', error = ? WHERE status IN ('queued','running')", (err,))
        conn.execute("UPDATE projects SET status = CASE WHEN EXISTS (SELECT 1 FROM content_pieces c WHERE c.project_id = "
                     "projects.id) OR EXISTS (SELECT 1 FROM clips k WHERE k.project_id = projects.id) "
                     "THEN 'ready' ELSE 'failed' END WHERE status = 'generating'")
