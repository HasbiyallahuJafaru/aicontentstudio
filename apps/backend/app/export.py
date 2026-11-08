"""Export (PRD §47, §68-73): one folder per piece under exports/<date>/ with renders, cover frame, caption and
platform-adapted metadata.json. File organization only - nothing is published (§48)."""
import csv
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import clips, config, content, platforms, projects, render
from app.clipper import select
from app.database import connect
from app.errors import UserError

EXPORTABLE = ("ready", "approved", "exported")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "piece"


def export_project(project_id: str, report=None, piece_ids: list[str] | None = None) -> dict:
    """Same (project_id, report) runner shape as content.generate / renders.render_project (jobs.py dispatch)."""
    brief = projects.get(project_id)["brief"]
    if brief.get("kind") == "clip":
        return _export_clips(project_id, report)
    all_pieces = content.pieces(project_id)
    pieces = [p for p in all_pieces if p["status"] in EXPORTABLE and (not piece_ids or p["id"] in piece_ids)]
    if not pieces:
        raise UserError("Nothing to export yet. Render the pieces first, then export.")

    slug = _slug(projects.get(project_id)["name"])
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = Path("exports") / date
    abs_root = config.DATA_DIR / root
    abs_root.mkdir(parents=True, exist_ok=True)

    n = len(pieces)
    exported = 0
    for i, piece in enumerate(pieces, 1):
        if report:
            report(f"Exporting piece {i} of {n}", (i - 0.5) / n)
        with connect() as conn:
            rows = conn.execute("SELECT kind, local_path FROM renders WHERE piece_id = ?", (piece["id"],)).fetchall()
        files = {"video_9x16.mp4": r["local_path"] for r in rows if r["kind"] == "video"}
        files.update({"image_4x5.jpg": r["local_path"] for r in rows if r["kind"] == "image"})
        if not files:
            continue  # nothing rendered for this piece; export the rest and say so in the summary
        folder = abs_root / f"{piece['idx']:03d}_{slug}"
        folder.mkdir(parents=True, exist_ok=True)
        for name, rel in files.items():
            shutil.copy2(config.MEDIA_DIR / rel, folder / name)
        if "video_9x16.mp4" in files:  # cover frame (PRD §71/§73); image pieces already are one
            render.thumbnail(folder / "video_9x16.mp4", folder / "thumbnail.jpg")
        else:
            shutil.copy2(folder / "image_4x5.jpg", folder / "thumbnail.jpg")

        meta = dict(piece["content"]["metadata"], theme=brief["topic"])
        blocks = {}
        for platform in brief["platforms"]:
            try:
                blocks[platform] = platforms.adapt(platform, meta, files)
            except UserError as e:  # e.g. feed needs the 4:5 image this piece never rendered
                blocks[platform] = {"unavailable": str(e)}
        (folder / "caption.txt").write_text(f'{meta["caption"]}\n\n'
                                            + " ".join(f"#{t.lstrip('#')}" for t in meta["hashtags"]),
                                            encoding="utf-8")
        (folder / "metadata.json").write_text(json.dumps({**meta, "platforms": blocks}, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        with connect() as conn:
            conn.execute("UPDATE content_pieces SET status = 'exported' WHERE id = ?", (piece["id"],))
        exported += 1
    if report:
        report("Done", 1.0)
    if not exported:
        raise UserError("None of the selected pieces have rendered outputs to export.")
    with connect() as conn:  # one row per run; the date folder holds every piece folder of the run
        conn.execute("INSERT INTO exports (id, project_id, dir, pieces) VALUES (?,?,?,?)",
                     (uuid.uuid4().hex[:12], project_id, str(root), exported))
    return {"dir": str(abs_root), "pieces": exported}


def _export_clips(project_id: str, report) -> dict:
    """Clip projects: one folder per clip (video, cover, caption file, metadata with the per-platform posts)."""
    rows = [c for c in clips.list_(project_id)
            if c["video_path"] and c["status"] in ("ready", "approved", "exported")]
    if not rows:
        raise UserError("Nothing to export yet. Wait for the clip job to finish, then export.")

    project = projects.get(project_id)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = Path("exports") / date
    abs_root = config.DATA_DIR / root
    abs_root.mkdir(parents=True, exist_ok=True)

    n = len(rows)
    for i, c in enumerate(rows, 1):
        if report:
            report(f"Exporting clip {i} of {n}", (i - 0.5) / n)
        folder = abs_root / f"{c['idx']:03d}_{_slug(c['title'])}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config.MEDIA_DIR / c["video_path"], folder / "clip.mp4")
        shutil.copy2(config.MEDIA_DIR / c["cover_path"], folder / "cover.jpg")
        ass = (config.MEDIA_DIR / c["video_path"]).with_suffix(".ass")
        if ass.exists():
            shutil.copy2(ass, folder / "captions.ass")
        (folder / "caption.txt").write_text(
            f"{c['title']}\n\n{c['description']}\n\n" + " ".join(c["hashtags"]), encoding="utf-8")
        meta = {"title": c["title"], "description": c["description"], "hook": c["hook"], "score": c["score"],
                "start": c["start_at"], "end": c["end_at"], "orientation": project["brief"]["orientation"],
                "source": project["brief"]["source"], "posts": c["posts"]}
        (folder / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        with connect() as conn:
            conn.execute("UPDATE clips SET status = 'exported' WHERE id = ?", (c["id"],))
    _clip_sheets(abs_root, project["name"], rows)
    if report:
        report("Done", 1.0)
    with connect() as conn:  # one row per run; the date folder holds every clip folder of the run
        conn.execute("INSERT INTO exports (id, project_id, dir, pieces) VALUES (?,?,?,?)",
                     (uuid.uuid4().hex[:12], project_id, str(root), n))
    return {"dir": str(abs_root), "pieces": n}


def _clip_sheets(root: Path, name: str, rows: list[dict]) -> None:
    """Every exported clip's copy in one table (ported from ClipperAi's package): <project>_clips.csv, one column
    per platform, with a BOM so Excel reads it as UTF-8, and the same as <project>_clips.json."""
    copy, facts = ["idx", "title", "hook", "description", "hashtags"], ["start_s", "end_s", "score", "reason"]
    table = [{"idx": c["idx"], "title": c["title"], "hook": c["hook"], "description": c["description"],
              "hashtags": " ".join(c["hashtags"]), **{n: c["posts"].get(n, "") for n in select.LIMITS},
              "start_s": round(c["start_at"], 2), "end_s": round(c["end_at"], 2), "score": c["score"],
              "reason": c["reason"]} for c in rows]
    with open(root / f"{_slug(name)}_clips.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, [*copy, *select.LIMITS, *facts])
        writer.writeheader()
        writer.writerows(table)
    (root / f"{_slug(name)}_clips.json").write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")


def delete(export_id: str) -> dict:
    """Delete one export: only this project's folders inside the dated export folder (other projects exported the
    same day share that folder and keep their files), and every record of this project in it."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
        if row is None:
            raise UserError("This export no longer exists.", f"export id {export_id}")
        project = conn.execute("SELECT name FROM projects WHERE id = ?", (row["project_id"],)).fetchone()
        titles = [r["title"] for r in conn.execute("SELECT title FROM clips WHERE project_id = ?", (row["project_id"],))]
    root = (config.DATA_DIR / row["dir"]).resolve()
    if config.DATA_DIR.resolve() not in root.parents:
        raise UserError("This export's folder is outside the app's data folder.", str(root))
    suffixes = {f"_{_slug(project['name'])}"} | {f"_{_slug(t)}" for t in titles}
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_dir() and folder.name[:3].isdigit() and any(folder.name.endswith(s) for s in suffixes):
                shutil.rmtree(folder)
        for ext in ("csv", "json"):  # the clip project's summary sheets
            (root / f"{_slug(project['name'])}_clips.{ext}").unlink(missing_ok=True)
        if not any(root.iterdir()):
            root.rmdir()
    with connect() as conn:  # a re-export the same day wrote into the same folders: those records go too
        conn.execute("DELETE FROM exports WHERE project_id = ? AND dir = ?", (row["project_id"], row["dir"]))
    return {"deleted": export_id}


def list_(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT e.id, e.project_id, e.dir, e.pieces, e.created_at, p.name AS project "
                            "FROM exports e JOIN projects p ON p.id = e.project_id "
                            "ORDER BY e.created_at DESC LIMIT ?", (limit,)).fetchall()
        # up to three of the project's rendered 4:5 images: the export shows what went out, not a folder icon
        # (a clip project has no image renders: its clips' cover frames stand in)
        def first3(pid):
            return [c[0] for c in conn.execute(
                "SELECT local_path FROM renders WHERE project_id = ? AND kind = 'image' ORDER BY created_at DESC LIMIT 3",
                (pid,)).fetchall()] or [c[0] for c in conn.execute(
                "SELECT cover_path FROM clips WHERE project_id = ? ORDER BY idx LIMIT 3", (pid,)).fetchall()]
        covers = {pid: first3(pid) for pid in {r["project_id"] for r in rows}}
    return [{**dict(r), "path": str(config.DATA_DIR / r["dir"]), "covers": covers[r["project_id"]]} for r in rows]
