"""Content generation pipeline (Milestone 2+3): brief → batch plan → one piece per plan item → one visual per piece."""
import json
import re
import uuid
from difflib import SequenceMatcher
from typing import Callable

from app import assets, config, projects
from app.creative.model import get_model
from app.creative.prompts import quotes_only
from app.creative.schemas import BatchPlan, PlanItem
from app.database import connect
from app.errors import UserError

SIMILAR = 0.75        # quote similarity ratio above which a line counts as a repeat
PLAN_CHUNK = 20       # pieces per planning call (BatchPlan allows 20)
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


def split_author(line: str) -> tuple[str, str | None]:
    """ "Waste no more time arguing. — Marcus Aurelius" -> (line, author). A plain line has no author.
    A CSV row pasted straight into the box ("He who is brave is free.","Seneca") splits the same way."""
    row = re.fullmatch(r'\s*["“](.+?)["”]\s*[,;\t]\s*["“]?([^"“”]*?)["”]?\s*', line)
    if row:
        who = row[2].strip()
        return row[1].strip(), who if 0 < len(who) <= 60 else None
    for sep in (" — ", " – ", " ~ ", " - "):
        if sep in line:
            text, _, who = line.rpartition(sep)
            who = who.strip()
            # a plain hyphen is often part of the line itself ("Work hard - play hard"): it only marks an author
            # when what follows reads like a name
            name_like = re.fullmatch(r"[A-Z][\w.'’]*(?:,? [\w.'’]+){0,5}", who) is not None
            if text.strip() and 0 < len(who) <= 60 and (sep != " - " or name_like):
                return text.strip(), who
    return line.strip(), None


def _signed(piece) -> bool:
    """Every AI-chosen quote names its real author (owner 2026-11-08); placeholders don't count."""
    who = (piece.quote.author or "").strip().lower()
    return bool(who) and who not in {"unknown", "anonymous", "anon", "n/a", "none", "null", "author"}


def _insert(project_id: str, idx: int, angle: str, quote: str, content: dict, status: str = "written") -> str:
    id = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute("INSERT INTO content_pieces (id, project_id, idx, status, angle, quote, content) VALUES (?,?,?,?,?,?,?)",
                     (id, project_id, idx, status, angle, quote, json.dumps(content, ensure_ascii=False)))
    return id


# pieces written per AI request: as many as fit one reply under the max-token budget (a quote piece is ~400 tokens,
# a narrated piece ~900). ponytail: fixed sizes; size by settings.ai_max_tokens if replies start running out of room.
WRITE_GROUP_QUOTES, WRITE_GROUP_VIDEO = 8, 4


def quote_plan(brief: dict, n: int) -> BatchPlan:
    """The fixed stand-in plan for quote images: no AI call. Each piece is "a quote" on the topic; the group prompt
    asks for a different facet and photo subject per quote, and the footage search reads visual_type from here."""
    subject = (brief.get("topic") or "the quotes given")[:80]
    item = PlanItem.model_construct(angle="quote", visual_subject=subject, visual_type="image", intensity="medium",
                                    narration_style="")
    return BatchPlan.model_construct(reading="", batch_theme=subject, pieces=[item] * n)

def generate(project_id: str, report: Callable[[str, float], None]) -> None:
    brief = projects.get(project_id)["brief"]
    n = brief["quantity"]
    model = get_model()
    history, openings = _history(200)
    total = 2 * n + 1  # write + visual per piece (+ the plan for videos); keeps the progress bar honest

    if quotes_only(brief):  # quote images aren't planned (owner 2026-11-08): the group request writes them directly
        plan = quote_plan(brief, n)
    elif brief.get("quotes"):  # the user's own lines (up to 100): planned 20 at a time, the plan schema's limit
        report(f"Planning {n} {'angle' if n == 1 else 'angles'}", 0.02)
        qs, plans = brief["quotes"], []
        for k in range(0, len(qs), PLAN_CHUNK):
            chunk = qs[k:k + PLAN_CHUNK]
            plans.append(model.plan_batch({**brief, "quantity": len(chunk), "quotes": chunk}, history[:30] + openings))
        plan = BatchPlan.model_construct(reading=plans[0].reading, batch_theme=plans[0].batch_theme,
                                         pieces=[p for pl in plans for p in pl.pieces])
    else:
        report(f"Planning {n} {'angle' if n == 1 else 'angles'}", 0.02)
        plan = model.plan_batch(brief, history[:30] + openings)

    with connect() as conn:  # the new plan replaces any earlier pieces of this project
        conn.execute("DELETE FROM content_pieces WHERE project_id = ?", (project_id,))
    batch: list[str] = []
    written: list[dict] = []
    own = [split_author(q) for q in brief.get("quotes") or []]
    group = WRITE_GROUP_QUOTES if quotes_only(brief) else WRITE_GROUP_VIDEO
    drafts: dict[int, object] = {}  # piece number -> what the group request wrote (None: write it on its own)
    for i, item in enumerate(plan.pieces, 1):
        if i not in drafts:  # one request writes the next group of pieces (owner: batch, not one call per piece)
            items = plan.pieces[i - 1:i - 1 + group]
            noun = ("quote", "quotes") if quotes_only(brief) else ("piece", "pieces")
            report(f"Writing {noun[1]} {i}-{i + len(items) - 1} of {n}" if len(items) > 1 else f"Writing {noun[0]} {i} of {n}",
                   i / total)
            given = [own[i - 1 + j] if i - 1 + j < len(own) else None for j in range(len(items))]
            drafts.update(zip(range(i, i + len(items)),
                              model.write_pieces(brief, plan, items, batch + history[:30] + openings, given)))
        avoid = batch + history[:30] + openings
        if i <= len(own):  # the user's own line: the AI writes around it, the text itself is never changed
            text, author = own[i - 1]
            piece = drafts[i] or model.write_piece({**brief, "given_quote": text, "given_author": author}, plan, item, avoid)
            piece.quote.text, piece.quote.author, repeat = text, author, None
            content = {"plan": item.model_dump(), "reading": plan.reading, **piece.model_dump()}
            batch.append(text)
            written.append({"id": _insert(project_id, i, item.angle, text, content), "content": content})
            continue
        piece, repeat, unsigned = drafts[i], None, False
        if piece is not None:
            repeat = too_similar(piece.quote.text, batch + history)
            unsigned = not _signed(piece)
        tries = 0 if piece is not None and not repeat and not unsigned else PIECE_ATTEMPTS - (piece is not None)
        for _ in range(tries):  # unusable, a repeat or a quote with no author: write it alone
            if repeat:
                avoid = [repeat] + avoid
            piece = model.write_piece(brief, plan, item, avoid)
            repeat = too_similar(piece.quote.text, batch + history)
            unsigned = not _signed(piece)
            if not repeat and not unsigned:
                break
        content = {"plan": item.model_dump(), "reading": plan.reading, **piece.model_dump()}
        if repeat or unsigned:
            why = (f'Every attempt repeated an earlier line: "{repeat}"' if repeat
                   else "Every attempt came back without a real author for the quote.")
            _insert(project_id, i, item.angle, piece.quote.text, {**content, "error": why}, status="failed")
        else:
            batch.append(piece.quote.text)
            if piece.narration:  # later groups in this batch must not open the same way either
                openings.append(piece.narration.text.splitlines()[0])
            written.append({"id": _insert(project_id, i, item.angle, piece.quote.text, content), "content": content})
    written = _drop_fakes(model, written, {t for t, _ in own})
    if written:
        # footage options only (thumbnails): nothing full-size downloads until the user confirms the picks
        assets.propose(brief, written, report)  # same (stage, 0..1) scale: it counts the same total steps
    report("Done", 1.0)


FAKE = "This quote couldn't be confirmed as a real line by its author, so it wasn't kept. Regenerate the quote."


def _drop_fakes(model, written: list[dict], own: set[str]) -> list[dict]:
    """Q1 (2026-11-09): one check over the batch's "real" quotes; a line the checker calls invented or
    misattributed fails its piece rather than going out under a famous name. The user's own lines are never checked."""
    check = [w for w in written if w["content"]["quote"]["text"] not in own]
    verdicts = model.verify_quotes([(w["content"]["quote"]["text"], w["content"]["quote"].get("author") or "")
                                    for w in check])
    fakes = {w["id"] for w, v in zip(check, verdicts) if v == "no"}
    with connect() as conn:
        for w in written:
            if w["id"] in fakes:
                conn.execute("UPDATE content_pieces SET status = 'failed', content = ? WHERE id = ?",
                             (json.dumps({**w["content"], "error": FAKE}, ensure_ascii=False), w["id"]))
    return [w for w in written if w["id"] not in fakes]


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


def delete_piece(piece_id: str) -> dict:
    """Delete one piece: its writing, its render files and its usage records (the project and the others stay)."""
    from app import jobs
    from app.publish import posts
    piece = _piece(piece_id)
    jobs.ensure_idle(piece["project_id"])
    posts.release(piece["project_id"], piece_id=piece_id)
    with connect() as conn:
        files = [r["local_path"] for r in conn.execute("SELECT local_path FROM renders WHERE piece_id = ?", (piece_id,))]
        conn.execute("DELETE FROM content_pieces WHERE id = ?", (piece_id,))  # renders + usage cascade
    for rel in files:
        (config.MEDIA_DIR / rel).unlink(missing_ok=True)
    return {"deleted": piece_id}


def regenerate(piece_id: str, scope: str) -> dict:
    """§43: redo exactly one component (quote/narration/design/visual). Everything else is left untouched."""
    from app import jobs
    piece = _piece(piece_id)
    jobs.ensure_idle(piece["project_id"], "changing it")  # a running render writes the piece back when done
    content_data = piece["content"]
    # a piece failed only for its quote (the fact check) still has its plan: a new quote is exactly the fix
    unverified = piece["status"] == "failed" and content_data.get("error") == FAKE
    if piece["status"] == "failed" and not (unverified and scope == "quote"):
        raise UserError("A failed piece has no base to regenerate from. Generate the project again.")
    brief = projects.get(piece["project_id"])["brief"]

    if scope == "visual":  # fresh footage options for review; the current footage stays until the user confirms
        assets.propose(brief, [{"id": piece_id, "content": content_data}], lambda stage, p: None)
        if content_data.get("visual_error"):
            raise UserError(content_data["visual_error"])
    elif scope == "design":  # the next design in the genre's rotation: instant, free, and visible on re-render
        from app import design
        quote = content_data["quote"]["text"]
        current = design.pick(content_data.get("image_design") or brief.get("image_design", "auto"), brief["tone"],
                              (content_data.get("design") or {}).get("composition"), piece["idx"] - 1, quote)
        content_data["image_design"] = design.another(current, brief["tone"], quote)
    elif scope in ("quote", "narration"):
        if scope == "narration" and quotes_only(brief):
            raise UserError("Quote images have no narration to redo.")
        model = get_model()
        if scope == "narration":  # new words around the SAME quote: the script lands on it and may say who said it
            brief = {**brief, "given_quote": content_data["quote"]["text"],
                     "given_author": content_data["quote"].get("author")}
        item = PlanItem.model_validate(content_data["plan"])
        plan = BatchPlan(reading=content_data.get("reading", ""), batch_theme=brief["topic"], pieces=[item])
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
        if scope == "quote" and model.verify_quotes([(fresh.quote.text, fresh.quote.author or "")]) == ["no"]:
            raise UserError(FAKE.replace("Regenerate the quote.", "Try again."), f'"{fresh.quote.text}"')
        new = fresh.model_dump()
        # a new quote takes what was written around it: the narration lands on the quote (and may name its author)
        # and the caption, title and alt text describe it, so keeping the old ones would contradict it on screen
        keys = {"quote": ["quote", "metadata", "narration", "hook", "callouts"], "narration": ["narration"]}[scope]
        for k in keys:
            if k in new and (k != "narration" or new[k]):
                content_data[k] = new[k]
    else:
        raise UserError("Unknown regeneration scope.", scope)

    if unverified:  # it skipped the footage step when it failed: propose footage now, as generation would have
        content_data.pop("error", None)
        assets.propose(brief, [{"id": piece_id, "content": content_data}], lambda stage, p: None)
    _rewrite(piece, "written")
    return _piece(piece_id)


def recent(limit: int = 3) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT c.id, c.quote, c.project_id, p.name AS project FROM content_pieces c JOIN projects p "
                            "ON p.id = c.project_id WHERE c.status = 'written' ORDER BY c.created_at DESC, c.rowid DESC "
                            "LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def showcase(limit: int = 7) -> list[dict]:
    """The Dashboard crowd: the newest pieces anywhere, each with its newest rendered image (or clip-free video
    cover) when it has one. Unrendered pieces come back with image None and show as drafts, so freshly generated
    content appears at once and a deleted render never poses as a finished post."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT c.id, c.quote, c.status, c.project_id, p.name AS project,
                 (SELECT r.local_path FROM renders r WHERE r.piece_id = c.id AND r.kind = 'image'
                  ORDER BY r.created_at DESC LIMIT 1) AS image
               FROM content_pieces c JOIN projects p ON p.id = c.project_id
               WHERE c.status != 'failed' ORDER BY c.created_at DESC, c.idx LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with connect() as conn:
        r = conn.execute("""SELECT (SELECT count(*) FROM projects) AS projects,
            (SELECT count(*) FROM content_pieces WHERE status != 'failed') AS pieces,
            (SELECT count(*) FROM content_pieces WHERE status != 'failed' AND date(created_at, 'localtime') = date('now', 'localtime')) AS today,
            (SELECT count(*) FROM projects WHERE status = 'generating') AS generating""").fetchone()
    return dict(r)
