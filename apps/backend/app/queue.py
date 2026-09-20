"""Content queue (PRD §46): pieces across projects with their stage, plus recent jobs."""
import json

from app.database import connect


def list_() -> dict:
    with connect() as conn:
        pieces = conn.execute(
            "SELECT c.id, c.idx, c.status, c.quote, c.project_id, p.name AS project, c.created_at, "
            "(SELECT count(*) FROM renders r WHERE r.piece_id = c.id) AS renders "
            "FROM content_pieces c JOIN projects p ON p.id = c.project_id "
            "ORDER BY c.rowid DESC LIMIT 200").fetchall()
        jobs = conn.execute(
            "SELECT j.*, p.name AS project FROM generation_jobs j JOIN projects p ON p.id = j.project_id "
            "ORDER BY j.created_at DESC LIMIT 50").fetchall()
    return {"pieces": [dict(r) for r in pieces],
            "jobs": [{**dict(j), "error": json.loads(j["error"]) if j["error"] else None} for j in jobs]}
