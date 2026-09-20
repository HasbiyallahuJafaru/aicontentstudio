"""Clip orchestration: runs the engine over a clip project's source video, records rows in `clips`, keeps the
transcript cached on disk by source key. Rides the shared job system (generation_jobs.kind = 'clip')."""
import json
import shutil
import uuid
from pathlib import Path

from app import config, projects
from app.clipper import acquire, select, transcribe
from app.clipper.render_clip import render as render_clip
from app.clipper.select import snap
from app.database import connect
from app.errors import UserError

WORK = "clipwork"  # under media/: downloaded sources + cached transcripts


def load_transcript(key: str) -> dict | None:
    p = config.MEDIA_DIR / WORK / key / "transcript.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_transcript(key: str, transcript: dict) -> None:
    p = config.MEDIA_DIR / WORK / key / "transcript.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")


def run(project_id: str, report) -> None:
    """Same (project_id, report) runner shape as content.generate / renders.render_project (jobs.py dispatch)."""
    b = projects.get(project_id)["brief"]
    out = config.MEDIA_DIR / "clips" / project_id
    with connect() as conn:  # a re-clip replaces the previous take
        conn.execute("DELETE FROM clips WHERE project_id = ?", (project_id,))
    if out.exists():
        shutil.rmtree(out)

    meta: dict = {}
    video, work = acquire.acquire(b["source"], config.MEDIA_DIR / WORK,
                                  lambda pct: report("Downloading", round(0.02 + 0.23 * pct / 100, 3)), meta)
    if meta.get("title"):  # the source's own title is the honest project name
        with connect() as conn:
            conn.execute("UPDATE projects SET name = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                         "WHERE id = ?", (meta["title"][:80], project_id))
    report("Transcribing", 0.25)
    transcript = load_transcript(work.name)
    if transcript is None:
        transcript = transcribe.transcribe(video, work)
        save_transcript(work.name, transcript)
    if not transcript["segments"]:
        raise UserError("No speech found in this video, so there is nothing to clip.")

    report("Finding the best moments", 0.5)
    n = b["n"] or max(3, min(30, round(transcript["segments"][-1]["end"] / 60)))  # about one clip per minute
    found = select.find_clips(transcript, n, b["min_len"], b["max_len"])

    out.mkdir(parents=True, exist_ok=True)
    total = len(found)
    for i, clip in enumerate(found, 1):
        report(f"Rendering clip {i} of {total}", round(0.55 + 0.45 * (i - 1) / total, 3))
        clip.start, clip.end = snap(clip.start, clip.end, transcript["words"])
        path = out / f"clip{i:02}.mp4"
        render_clip(video, max(0, clip.start - 0.1), clip.end + 0.2, path, transcript["words"],
                    b["burn_captions"], b["orientation"], fps=b["fps"])
        with connect() as conn:
            conn.execute("INSERT INTO clips (id, project_id, idx, start_at, end_at, score, reason, hook, title, "
                         "description, hashtags, posts, video_path, cover_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (uuid.uuid4().hex[:12], project_id, i, clip.start, clip.end, clip.score, clip.reason,
                          clip.hook, clip.title, clip.description, json.dumps(clip.hashtags, ensure_ascii=False),
                          clip.posts.model_dump_json(), _rel(path), _rel(path.with_suffix(".jpg"))))
    report("Done", 1.0)


def _rel(path: Path) -> str:
    return path.relative_to(config.MEDIA_DIR).as_posix()


def list_(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM clips WHERE project_id = ? ORDER BY idx", (project_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["hashtags"] = json.loads(d["hashtags"])
        d["posts"] = json.loads(d["posts"])
        out.append(d)
    return out


def review(id: str, status: str) -> dict:
    if status not in ("ready", "approved", "rejected"):
        raise UserError("Unknown clip status.", status)
    with connect() as conn:
        if conn.execute("UPDATE clips SET status = ? WHERE id = ?", (status, id)).rowcount == 0:
            raise UserError("This clip no longer exists.", id)
    return {"id": id, "status": status}
