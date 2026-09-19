"""Content generation pipeline (Milestone 2+3): brief → batch plan → one piece per plan item → one visual per piece."""
import json
import re
import uuid
from difflib import SequenceMatcher
from typing import Callable

from app import assets, projects
from app.creative.model import get_model
from app.database import connect

SIMILAR = 0.75        # quote similarity ratio above which a line counts as a repeat
PIECE_ATTEMPTS = 3    # PRD §78: bounded regeneration when a quote repeats history


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def too_similar(quote: str, history: list[str]) -> str | None:
    """Return the history line this quote repeats, if any. ponytail: difflib over ~200 lines; embeddings if history grows large."""
    q = _norm(quote)
    for h in history:
        if SequenceMatcher(None, q, _norm(h)).ratio() >= SIMILAR:
            return h
    return None


def _history(limit: int) -> tuple[list[str], list[str]]:
    """Recent quotes, and recent narration openings (first sentence), newest first."""
    with connect() as conn:
        rows = conn.execute("SELECT quote, json_extract(content, '$.narration.text') AS n FROM content_pieces "
                            "WHERE status != 'failed' ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [r["quote"] for r in rows], [re.split(r"(?<=[.!?])\s", r["n"] or "", maxsplit=1)[0] for r in rows[:20]]


def _insert(project_id: str, idx: int, angle: str, quote: str, content: dict, status: str = "written") -> str:
    id = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute("INSERT INTO content_pieces (id, project_id, idx, status, angle, quote, content) VALUES (?,?,?,?,?,?,?)",
                     (id, project_id, idx, status, angle, quote, json.dumps(content, ensure_ascii=False)))
    return id


def generate(project_id: str, report: Callable[[str, float], None]) -> None:
    brief = projects.get(project_id)["brief"]
    n = brief["quantity"]
    model = get_model()
    history, openings = _history(200)
    total = 2 * n + 1  # plan + write + visual per piece; keeps the progress bar honest through both phases

    report(f"Planning {n} {'angle' if n == 1 else 'angles'}", 0.02)
    plan = model.plan_batch(brief, history[:30] + openings)

    with connect() as conn:  # the new plan replaces any earlier pieces of this project
        conn.execute("DELETE FROM content_pieces WHERE project_id = ?", (project_id,))
    batch: list[str] = []
    written: list[dict] = []
    for i, item in enumerate(plan.pieces, 1):
        report(f"Writing piece {i} of {n}", i / total)
        avoid = batch + history[:30] + openings
        for _ in range(PIECE_ATTEMPTS):
            piece = model.write_piece(brief, plan, item, avoid)
            repeat = too_similar(piece.quote.text, batch + history)
            if not repeat:
                break
            avoid = [repeat] + avoid
        content = {"plan": item.model_dump(), **piece.model_dump()}
        if repeat:
            _insert(project_id, i, item.angle, piece.quote.text,
                    {**content, "error": f'Every attempt repeated an earlier line: "{repeat}"'}, status="failed")
        else:
            batch.append(piece.quote.text)
            written.append({"id": _insert(project_id, i, item.angle, piece.quote.text, content), "content": content})
    if written:
        assets.assign(brief, written, report)  # same (stage, 0..1) scale: it counts the same total steps
    report("Done", 1.0)


def pieces(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM content_pieces WHERE project_id = ? ORDER BY idx", (project_id,)).fetchall()
    return [{**dict(r), "content": json.loads(r["content"])} for r in rows]


def recent(limit: int = 3) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT c.id, c.quote, c.project_id, p.name AS project FROM content_pieces c JOIN projects p "
                            "ON p.id = c.project_id WHERE c.status = 'written' ORDER BY c.created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with connect() as conn:
        r = conn.execute("""SELECT (SELECT count(*) FROM projects) AS projects,
            (SELECT count(*) FROM content_pieces WHERE status != 'failed') AS pieces,
            (SELECT count(*) FROM content_pieces WHERE status != 'failed' AND date(created_at, 'localtime') = date('now', 'localtime')) AS today,
            (SELECT count(*) FROM projects WHERE status = 'generating') AS generating""").fetchone()
    return dict(r)
