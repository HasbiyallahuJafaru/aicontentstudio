"""Render orchestration (PRD §33): narration per piece, then video/image outputs, validated and recorded.

Rides the shared job system (generation_jobs.kind = 'render'); piece status walks written -> rendering -> ready.
"""
import asyncio
import json
import shutil
import uuid
from pathlib import Path

from app import config, content, edit, projects, render, settings, tts
from app.database import connect
from app.errors import UserError


def _assets_for(piece: dict) -> list[dict]:
    """The piece's shot pool, in planned order. Pieces written before the pool carry a single `asset`."""
    content_data = piece["content"]
    entries = content_data.get("assets") or ([content_data["asset"]] if content_data.get("asset") else [])
    ids = [e["id"] for e in entries if e.get("id")]
    if not ids:
        return []
    with connect() as conn:
        rows = {r["id"]: dict(r) for r in conn.execute(
            f"SELECT * FROM assets WHERE id IN ({','.join('?' * len(ids))})", ids)}
    return [rows[i] for i in ids if i in rows]


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


def _words(text: str, audio, duration: float) -> list[dict]:
    """Word timings for the narration. Real ones when a Groq key is set (the same STT the clip engine uses),
    estimated from word length otherwise. They drive both the karaoke captions and where the edit cuts."""
    if config.SECRETS.get("GROQ_API_KEY"):
        try:
            from app.clipper.transcribe import transcribe
            return transcribe(audio, config.MEDIA_DIR / "tmp" / "narration")["words"]
        except UserError:
            pass  # STT is a nicety here, not the job: fall back rather than fail a render over it
    tokens = [w for w in text.split() if w]
    total = sum(len(w) + 1 for w in tokens) or 1
    words, t = [], 0.0
    for w in tokens:
        span = duration * (len(w) + 1) / total
        words.append({"word": w, "start": round(t, 3), "end": round(min(t + span * 0.9, duration), 3)})
        t += span
    return words


def _shots_for(assets: list[dict], duration: float, words: list[dict], tone: str) -> list[dict]:
    """The edit plan turned into ffmpeg shots: which file, where to enter it, how long it holds, how it moves.
    An asset used more than once enters at a different point each time, so a repeat is a new angle, not a loop."""
    shots = []
    for s in edit.plan(assets, duration, words, tone):
        a = s["asset"]
        still = a["asset_type"] == "image"
        shot = {"src": str(config.MEDIA_DIR / a["local_path"]), "seek": 0.0, "length": s["length"],
                "still": still, "motion": "push" if still else s["motion"], "speed": s["speed"]}
        if not still:
            avail = max(a["duration"] or duration, 0.5)
            shot["seek"] = round(avail * s["nth"] / max(s["of"], 1), 2)
            shot["loop"] = shot["seek"] + s["length"] / s["speed"] > avail
        if "transition" in s:
            shot["transition"], shot["tdur"] = s["transition"], s["tdur"]
        shots.append(shot)
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
    if shutil.which(config.FFMPEG) is None and not Path(config.FFMPEG).exists():
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
            pool = _assets_for(piece)
            if not pool:
                raise UserError("This piece has no visual asset yet.", "Generate visuals, then render again.")
            asset = pool[0]  # the hero shot: it also feeds the 4:5 image render
            report(f"Rendering {i} of {n}", i / n)
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'rendering' WHERE id = ?", (piece["id"],))
            for kind in _wanted_kinds(brief, piece):
                out = Path("renders") / project_id / f"{piece['idx']:03d}-{kind}.{'mp4' if kind == 'video' else 'jpg'}"
                full_out = config.MEDIA_DIR / out
                try:
                    if kind == "video":
                        # clean video: no scrim, no quote text burned in (user decision 2026-09-20)
                        timeline = narration.duration + edit.TAIL
                        words = _words(content_data["narration"]["text"], narration.path, narration.duration)
                        subs = _subtitles_ass(piece, words, timeline,
                                              renderer.w, renderer.h) if brief["subtitles"] else None
                        cut = edit.cut_for(brief["tone"])
                        look = cut["look"] if brief["look_filter"] == "auto" else brief["look_filter"]
                        info = renderer.render_video(src=config.MEDIA_DIR / asset["local_path"],
                                                     narration=narration.path, out=full_out,
                                                     subject_position=asset["subject_position"] or "center",
                                                     src_fps=asset["fps"], src_duration=asset["duration"],
                                                     still=asset["asset_type"] == "image", progress=None,
                                                     out_fps=brief["fps"], look=look, duck=cut["duck"],
                                                     blur_background=brief["blur_background"],
                                                     parallax=brief["parallax"], subtitles=subs,
                                                     shots=_shots_for(pool, timeline, words, brief["tone"]))
                        duration, fps, w, h = info["duration"], info["fps"], renderer.w, renderer.h
                    else:
                        image_src = config.MEDIA_DIR / asset["local_path"]
                        if asset["asset_type"] == "video":
                            # a video asset can't feed PIL: grab a representative frame and render the 4:5 from it
                            image_src = config.MEDIA_DIR / "tmp" / f"{piece['id']}-frame.jpg"
                            render.thumbnail(config.MEDIA_DIR / asset["local_path"], image_src,
                                             at=max((asset["duration"] or 0) / 2, 0.5))
                        renderer.render_image(src=image_src, out=full_out,
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


def _subtitles_ass(piece: dict, words: list[dict], duration: float, w: int, h: int) -> Path:
    """Burn-ready ASS for the narration, from the same word timings the edit cut to."""
    from app.clipper.captions import captions
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
