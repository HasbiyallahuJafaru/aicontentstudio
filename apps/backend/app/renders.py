"""Render orchestration (PRD §33): narration per piece, then video/image outputs, validated and recorded.

Rides the shared job system (generation_jobs.kind = 'render'); piece status walks written -> rendering -> ready.
"""
import asyncio
import json
import shutil
import uuid
from pathlib import Path

from app import config, content, projects, render, settings, tts
from app.database import connect
from app.errors import UserError


def _asset_for(piece: dict) -> dict | None:
    asset_id = piece["content"].get("asset", {}).get("id")
    if not asset_id:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row else None


def _wanted_kinds(brief: dict, piece: dict) -> list[str]:
    """video_image renders both; explicit format forces one; otherwise the plan's preferred type."""
    if brief["format"] == "video_image":
        return ["video", "image"]
    if brief["format"] in ("video", "image"):
        return [brief["format"]]
    return [piece["content"]["visual"]["preferred_type"]]


def render_project(project_id: str, report) -> None:
    pieces = [p for p in content.pieces(project_id) if p["status"] != "failed"]
    if not pieces:
        raise UserError("Nothing to render yet. Generate content first.")
    brief = projects.get(project_id)["brief"]
    s = settings.get()
    renderer = render.FFmpegRenderer(s["render_crf"], s["render_audio_bitrate"],
                                     Path(s["music_path"]) if s["music_path"] else None, s["music_volume"],
                                     s["render_width"], s["render_height"])
    engine = tts.get_tts()
    if shutil.which("ffmpeg") is None:
        raise UserError("FFmpeg is not installed or not on PATH.", "Install ffmpeg and restart the app.")

    n = len(pieces)
    for i, piece in enumerate(pieces, 1):
        report(f"Narration {i} of {n}", (i - 0.5) / n)
        content_data = piece["content"]
        try:
            narration = asyncio.run(engine.generate(content_data["narration"]["text"], s["tts_voice"],
                                                    s["tts_speed"]))
            asset = _asset_for(piece)
            if asset is None:
                raise UserError("This piece has no visual asset yet.", "Generate visuals, then render again.")
            report(f"Rendering {i} of {n}", i / n)
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'rendering' WHERE id = ?", (piece["id"],))
            for kind in _wanted_kinds(brief, piece):
                out = Path("renders") / project_id / f"{piece['idx']:03d}-{kind}.{'mp4' if kind == 'video' else 'jpg'}"
                full_out = config.MEDIA_DIR / out
                try:
                    if kind == "video":
                        scrim_png = render.scrim(config.MEDIA_DIR / "tmp" / f"{piece['id']}-scrim.png",
                                                 content_data["palette"]["overlay"], renderer.w, renderer.h,
                                                 (30, 190))
                        info = renderer.render_video(
                            src=config.MEDIA_DIR / asset["local_path"], narration=narration.path,
                            scrim_png=scrim_png, out=full_out, quote=content_data["quote"]["text"],
                            subject_position=asset["subject_position"] or "center",
                            palette=content_data["palette"], src_fps=asset["fps"],
                            src_duration=asset["duration"], still=asset["asset_type"] == "image",
                            progress=None)
                        duration = info["duration"]
                    else:
                        renderer.render_image(src=config.MEDIA_DIR / asset["local_path"], out=full_out,
                                              quote=content_data["quote"]["text"],
                                              subject_position=asset["subject_position"] or "center",
                                              palette=content_data["palette"])
                        duration = None
                except UserError as e:
                    raise UserError(f"Piece {piece['idx']} ({kind}) failed to render: {e}", e.detail)
                with connect() as conn:
                    conn.execute("INSERT OR REPLACE INTO renders (id, project_id, piece_id, kind, local_path, duration) "
                                 "VALUES (?,?,?,?,?,?)",
                                 (uuid.uuid4().hex[:12], project_id, piece["id"], kind, out.as_posix(), duration))
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'ready' WHERE id = ?", (piece["id"],))
            piece["status"] = "ready"
        except UserError as e:
            content_data["render_error"] = str(e)
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'written', content = ? WHERE id = ?",
                             (json.dumps(content_data, ensure_ascii=False), piece["id"]))
    report("Done", 1.0)


def list_(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT r.id, r.piece_id, r.kind, r.local_path, r.duration, r.created_at, "
                            "c.idx FROM renders r JOIN content_pieces c ON c.id = r.piece_id "
                            "WHERE r.project_id = ? ORDER BY c.idx, r.kind", (project_id,)).fetchall()
    return [dict(r) for r in rows]
