"""Content generation pipeline (Milestone 2+3): brief → batch plan → one piece per plan item → one visual per piece."""
import json
import re
import uuid
from difflib import SequenceMatcher
from typing import Callable

from app import assets, projects
from app.creative.model import get_model
from app.creative.schemas import BatchPlan, PlanItem
from app.database import connect
from app.errors import UserError

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


def _piece(piece_id: str) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM content_pieces WHERE id = ?", (piece_id,)).fetchone()
    if row is None:
        raise UserError("This piece no longer exists.", f"piece id {piece_id}")
    return {**dict(row), "content": json.loads(row["content"])}


def _rewrite(piece: dict, status: str) -> None:
    """Persist content + status; dropping to 'written' makes the existing renders stale, so they go too."""
    with connect() as conn:
        if status == "written":
            conn.execute("DELETE FROM renders WHERE piece_id = ?", (piece["id"],))
        conn.execute("UPDATE content_pieces SET status = ?, quote = ?, content = ? WHERE id = ?",
                     (status, piece["content"]["quote"]["text"],
                      json.dumps(piece["content"], ensure_ascii=False), piece["id"]))


def regenerate(piece_id: str, scope: str) -> dict:
    """§43: redo exactly one component (quote/narration/design/visual). Everything else is left untouched."""
    piece = _piece(piece_id)
    if piece["status"] == "failed":
        raise UserError("A failed piece has no base to regenerate from. Generate the project again.")
    content_data = piece["content"]
    brief = projects.get(piece["project_id"])["brief"]

    if scope == "visual":  # find another visual: the cooldown pushes away from the current asset (PRD §18)
        old_asset = (content_data.get("asset") or {}).get("id")
        assets.assign(brief, [{"id": piece_id, "content": content_data}], lambda stage, p: None)
        if (content_data.get("asset") or {}).get("id") == old_asset:
            raise UserError("The visual pool for this search is exhausted; every candidate is already in use.",
                            content_data["visual"]["search_query"])
    elif scope in ("quote", "narration", "design"):
        model = get_model()
        item = PlanItem.model_validate(content_data["plan"])
        plan = BatchPlan(batch_theme=brief["topic"], pieces=[item])
        history, openings = _history(200)
        avoid = history[:30] + openings
        fresh, repeat = None, None
        for _ in range(PIECE_ATTEMPTS if scope == "quote" else 1):
            fresh = model.write_piece(brief, plan, item, avoid)
            repeat = too_similar(fresh.quote.text, history) if scope == "quote" else None
            if not repeat:
                break
            avoid = [fresh.quote.text] + avoid
        if repeat:
            raise UserError("Every attempt repeated an earlier line.", f'"{repeat}"')
        content_data[scope] = fresh.model_dump()[scope]
    else:
        raise UserError("Unknown regeneration scope.", scope)

    _rewrite(piece, "written")
    return _piece(piece_id)


def approve(piece_id: str) -> dict:
    """§41: approve a rendered piece; approval is what the export step is allowed to rely on."""
    piece = _piece(piece_id)
    if piece["status"] not in ("ready", "approved"):
        raise UserError("Only rendered pieces can be approved.", f"this piece is '{piece['status']}'")
    with connect() as conn:
        conn.execute("UPDATE content_pieces SET status = 'approved' WHERE id = ?", (piece_id,))
    return _piece(piece_id)


def recent(limit: int = 3) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT c.id, c.quote, c.project_id, p.name AS project FROM content_pieces c JOIN projects p "
                            "ON p.id = c.project_id WHERE c.status = 'written' ORDER BY c.created_at DESC, c.rowid DESC "
                            "LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with connect() as conn:
        r = conn.execute("""SELECT (SELECT count(*) FROM projects) AS projects,
            (SELECT count(*) FROM content_pieces WHERE status != 'failed') AS pieces,
            (SELECT count(*) FROM content_pieces WHERE status != 'failed' AND date(created_at, 'localtime') = date('now', 'localtime')) AS today,
            (SELECT count(*) FROM projects WHERE status = 'generating') AS generating""").fetchone()
    return dict(r)
