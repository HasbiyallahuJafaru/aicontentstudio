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
    """video_image renders both; explicit format forces one; otherwise the plan's preferred type.
    Instagram Feed is a 4:5 image post (PRD §72), so targeting it always renders the image as well."""
    if brief["format"] in ("video", "image"):
        kinds = [brief["format"]]
    elif brief["format"] == "video_image":
        kinds = ["video", "image"]
    else:
        kinds = [piece["content"]["visual"]["preferred_type"]]
    kinds += ["image"] if "instagram_feed" in brief["platforms"] else []
    return sorted(set(kinds), key=lambda k: k != "video")


GENRE_LOOKS = {"hope": "warm", "speech": "vivid", "stoic": "cool", "history": "mono", "books": "cool",
               "cinema": "mono"}


def _shots_for(asset: dict, duration: float) -> list[dict]:
    """The edit plan for a video piece: the asset is cut into 2-3 motion shots (zoom in / pan / zoom out) and a
    still cutaway made from its own cover frame is merged in the middle — video and image in one timeline, the
    way the top motivational edits are cut. Short sources loop instead of running out mid-shot."""
    src = config.MEDIA_DIR / asset["local_path"]
    if asset["asset_type"] == "image":
        return [{"src": str(src), "seek": 0.0, "length": duration, "still": True, "motion": "push"}]
    avail = max(asset["duration"] or duration, 0.5)
    n = 3 if duration >= 16 else 2
    seg = duration / n
    shots = []
    for i in range(n):
        seek = round(avail * i / n, 2)
        shots.append({"src": str(src), "seek": seek, "length": round(seg, 3), "still": False,
                      "motion": ("in", "pan", "out")[i % 3], "loop": seek + seg > avail})
    if asset.get("thumb_path") and duration >= 9:  # the still cutaway: one beat, with a push-in
        shots.insert(1 if len(shots) > 1 else 0,
                     {"src": str(config.MEDIA_DIR / asset["thumb_path"]), "seek": 0.0,
                      "length": round(min(1.4, duration / n), 3), "still": True, "motion": "push"})
    return shots


def render_project(project_id: str, report, piece_ids: list[str] | None = None) -> None:
    pieces = [p for p in content.pieces(project_id) if p["status"] != "failed"
              and (not piece_ids or p["id"] in piece_ids)]
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

    # the brief's narration voice ("engine:voice") overrides the Settings default for this project
    voice_engine, _, voice_name = (brief.get("voice") or "").partition(":")
    if voice_engine:
        engine = tts.get_tts(voice_engine)
    voice = voice_name or s["tts_voice"]

    n = len(pieces)
    for i, piece in enumerate(pieces, 1):
        report(f"Narration {i} of {n}", (i - 0.5) / n)
        content_data = piece["content"]
        try:
            narration = asyncio.run(engine.generate(content_data["narration"]["text"], voice, s["tts_speed"]))
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
                        # clean video: no scrim, no quote text burned in (user decision 2026-09-20)
                        subs = _subtitles_ass(piece, content_data["narration"]["text"], narration.duration,
                                              renderer.w, renderer.h) if brief["subtitles"] else None
                        look = brief["look_filter"]
                        if look == "auto":  # each genre carries its own grade
                            look = GENRE_LOOKS.get(brief["tone"], "none")
                        info = renderer.render_video(src=config.MEDIA_DIR / asset["local_path"],
                                                     narration=narration.path, out=full_out,
                                                     subject_position=asset["subject_position"] or "center",
                                                     src_fps=asset["fps"], src_duration=asset["duration"],
                                                     still=asset["asset_type"] == "image", progress=None,
                                                     out_fps=brief["fps"], look=look,
                                                     blur_background=brief["blur_background"],
                                                     parallax=brief["parallax"], subtitles=subs,
                                                     shots=_shots_for(asset, narration.duration + 0.6))
                        duration, fps, w, h = info["duration"], info["fps"], renderer.w, renderer.h
                    else:
                        renderer.render_image(src=config.MEDIA_DIR / asset["local_path"], out=full_out,
                                              quote=content_data["quote"]["text"],
                                              subject_position=asset["subject_position"] or "center",
                                              palette=content_data["palette"])
                        duration, fps, w, h = None, None, render.IMAGE_W, render.IMAGE_H
                except UserError as e:
                    raise UserError(f"Piece {piece['idx']} ({kind}) failed to render: {e}", e.detail)
                with connect() as conn:  # one row per piece+kind: a re-render replaces the stale output
                    conn.execute("DELETE FROM renders WHERE piece_id = ? AND kind = ?", (piece["id"], kind))
                    conn.execute("INSERT INTO renders (id, project_id, piece_id, kind, local_path, duration, "
                                 "fps, width, height) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (uuid.uuid4().hex[:12], project_id, piece["id"], kind, out.as_posix(), duration,
                                  fps, w, h))
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'ready' WHERE id = ?", (piece["id"],))
            piece["status"] = "ready"
        except UserError as e:
            content_data["render_error"] = str(e)
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'written', content = ? WHERE id = ?",
                             (json.dumps(content_data, ensure_ascii=False), piece["id"]))
    report("Done", 1.0)


def _subtitles_ass(piece: dict, text: str, duration: float, w: int, h: int) -> Path:
    """Burn-ready ASS for the narration: word timings estimated from the audio length, weighted by word length
    (ponytail: real per-word timestamps need forced alignment; Whisper gives them only for clip projects)."""
    from app.clipper.captions import captions
    words = []
    tokens = [w for w in text.split() if w]
    total = sum(len(w) + 1 for w in tokens) or 1
    t = 0.0
    for w in tokens:
        span = duration * (len(w) + 1) / total
        words.append({"word": w, "start": round(t, 3), "end": round(min(t + span * 0.9, duration), 3)})
        t += span
    ass = captions(words, 0.0, duration, w, h)
    path = config.MEDIA_DIR / "tmp" / f"{piece['id']}-subs.ass"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ass, encoding="utf-8")
    return path


def list_(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT r.id, r.piece_id, r.kind, r.local_path, r.duration, r.fps, r.width, r.height, "
                            "r.created_at, c.idx FROM renders r JOIN content_pieces c ON c.id = r.piece_id "
                            "WHERE r.project_id = ? ORDER BY c.idx, r.kind", (project_id,)).fetchall()
    return [dict(r) for r in rows]
