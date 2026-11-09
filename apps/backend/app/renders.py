"""Render orchestration (PRD §33): narration per piece, then video/image outputs, validated and recorded.

Rides the shared job system (generation_jobs.kind = 'render'); piece status walks written -> rendering -> ready.
"""
import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path

from app import config, content, design, edit, motion, projects, render, settings, tts
from app.database import connect
from app.errors import Cancelled, UserError, explain

log = logging.getLogger("renders")


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
    """Word timings for the narration. Real ones when an OpenRouter key is set (the same STT the clip engine uses),
    estimated from word length otherwise. They drive both the karaoke captions and where the edit cuts."""
    from app.clipper.transcribe import estimate_words, transcribe
    if config.SECRETS.get("OPENROUTER_API_KEY"):
        try:
            return transcribe(audio, config.MEDIA_DIR / "tmp" / "narration")["words"]
        except UserError:
            pass  # STT is a nicety here, not the job: fall back rather than fail a render over it
    return estimate_words(text, 0.0, duration)


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

    # the project's narration voice; briefs saved before Gemini hold "engine:voice" pairs (kokoro:af_heart),
    # which fall back to the default voice
    voice = (brief.get("voice") or "").rpartition(":")[2]
    voice = voice if voice in tts.VOICES else tts.DEFAULT_VOICE

    n = len(pieces)
    fail = getattr(report, "fail", None)  # jobs.py's report can mark one step failed and carry on
    for i, piece in enumerate(pieces, 1):
        content_data = piece["content"]
        kinds = _wanted_kinds(brief, piece)

        def at(step: str, f: float, i=i, piece=piece) -> None:
            # "Piece 3 (2 of 5): Encoding video": the piece number matches the list, the count shows the way left
            report(f"Piece {piece['idx']} ({i} of {n}): {step}", (i - 1 + min(max(f, 0.0), 1.0)) / n)

        # each piece's share of the bar: narration and word timings first, ffmpeg's encode is the long part
        enc = (0.45, 0.95 if "image" in kinds else 1.0) if "video" in kinds else None
        try:
            narration = None
            if "video" in kinds:  # a quote image has no voice: never pay for (or wait on) narration it won't use
                at("Narrating", 0.0)
                narration = asyncio.run(engine.generate(content_data["narration"]["text"], voice,
                                                        content_data["narration"].get("delivery", "")))
            pool = _assets_for(piece)
            if not pool:
                raise UserError("This piece has no visual asset yet.", "Generate visuals, then render again.")
            asset = pool[0]  # the hero shot: it also feeds the 4:5 image render
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'rendering' WHERE id = ?", (piece["id"],))
            for kind in kinds:
                out = Path("renders") / project_id / f"{piece['idx']:03d}-{kind}.{'mp4' if kind == 'video' else 'jpg'}"
                full_out = config.MEDIA_DIR / out
                try:
                    if kind == "video":
                        # clean video: no scrim, no quote text burned in (user decision 2026-09-20)
                        timeline = narration.duration + edit.TAIL
                        at("Timing the words", 0.25)
                        words = _words(content_data["narration"]["text"], narration.path, narration.duration)
                        subs = _subtitles_ass(piece, words, timeline, renderer.w, renderer.h,
                                              brief.get("captions")) if brief["subtitles"] else None
                        cut = edit.cut_for(brief["tone"])
                        look = cut["look"] if brief["look_filter"] == "auto" else brief["look_filter"]
                        at("Animating titles", 0.35)
                        callouts = [(c["text"], t) for c in content_data.get("callouts") or []
                                    if (t := motion.anchor_time(words, c["word"])) is not None]
                        layers = motion.layers(brief["tone"], renderer.w, renderer.h,
                                               content_data.get("hook") or "", callouts)
                        at("Encoding video", enc[0])
                        info = renderer.render_video(src=config.MEDIA_DIR / asset["local_path"],
                                                     narration=narration.path, out=full_out,
                                                     subject_position=asset["subject_position"] or "center",
                                                     src_fps=asset["fps"], src_duration=asset["duration"],
                                                     still=asset["asset_type"] == "image",
                                                     progress=lambda f: at("Encoding video", enc[0] + f * (enc[1] - enc[0])),
                                                     out_fps=brief["fps"], look=look, duck=cut["duck"],
                                                     blur_background=brief["blur_background"],
                                                     parallax=brief["parallax"], subtitles=subs,
                                                     shots=_shots_for(pool, timeline, words, brief["tone"]),
                                                     layers=layers)
                        duration, fps, w, h = info["duration"], info["fps"], renderer.w, renderer.h
                    else:
                        at("Designing the picture", enc[1] if enc else 0.1)
                        image_src = config.MEDIA_DIR / asset["local_path"]
                        if asset["asset_type"] == "video":
                            # a video asset can't feed PIL: grab a representative frame and render the 4:5 from it
                            image_src = config.MEDIA_DIR / "tmp" / f"{piece['id']}-frame.jpg"
                            render.thumbnail(config.MEDIA_DIR / asset["local_path"], image_src,
                                             at=max((asset["duration"] or 0) / 2, 0.5))
                        quote = content_data["quote"]
                        chosen = design.pick(content_data.get("image_design") or brief.get("image_design", "auto"),
                                             brief["tone"], (content_data.get("design") or {}).get("composition"),
                                             piece["idx"] - 1, quote["text"])
                        renderer.render_image(src=image_src, out=full_out, quote=quote,
                                              subject_position=asset["subject_position"] or "center",
                                              palette=content_data["palette"], design_name=chosen,
                                              face=brief.get("image_font", "auto"),
                                              position=brief.get("image_position", "auto"))
                        duration, fps, w, h = None, None, render.IMAGE_W, render.IMAGE_H
                except UserError as e:
                    raise UserError(f"Piece {piece['idx']} ({kind}) failed to render: {e}", e.detail)
                with connect() as conn:  # one row per piece+kind: a re-render replaces the stale output
                    conn.execute("DELETE FROM renders WHERE piece_id = ? AND kind = ?", (piece["id"], kind))
                    conn.execute("INSERT INTO renders (id, project_id, piece_id, kind, local_path, duration, "
                                 "fps, width, height) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (uuid.uuid4().hex[:12], project_id, piece["id"], kind, out.as_posix(), duration,
                                  fps, w, h))
            stale = content_data.pop("render_error", None) is not None
            content_data.pop("render_error_detail", None)
            with connect() as conn:
                if stale:  # an earlier failed render's note no longer applies
                    conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                                 (json.dumps(content_data, ensure_ascii=False), piece["id"]))
                conn.execute("UPDATE content_pieces SET status = 'ready' WHERE id = ?", (piece["id"],))
            piece["status"] = "ready"
        except Cancelled:
            raise
        except Exception as e:  # one bad piece never sinks the batch: log it on the step and on the piece
            if not isinstance(e, UserError):
                log.exception("render of piece %s failed", piece["id"])
            message, detail = (str(e), e.detail) if isinstance(e, UserError) else explain(e)
            if fail:
                fail(message, detail)
            content_data["render_error"] = message
            content_data["render_error_detail"] = detail
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET status = 'written', content = ? WHERE id = ?",
                             (json.dumps(content_data, ensure_ascii=False), piece["id"]))
    report("Done", 1.0)


def _subtitles_ass(piece: dict, words: list[dict], duration: float, w: int, h: int,
                   style: dict | None = None) -> Path:
    """Burn-ready ASS for the narration, from the same word timings the edit cut to, in the brief's caption style.
    Key words (the callout words) take the highlight; "palette" uses the project accent."""
    from app.clipper.captions import captions
    c = piece["content"]
    keys = [x.get("word", "") for x in c.get("callouts") or []]
    pal = c.get("palette") or {}
    ass = captions(words, 0.0, duration, w, h, keys, style, accent=design.accent(pal) if pal else "#E0B07A",
                   plate=pal.get("dark", "#111111"))
    path = config.MEDIA_DIR / "tmp" / f"{piece['id']}-subs.ass"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ass, encoding="utf-8")
    return path


def delete(render_id: str) -> dict:
    """Delete one rendered file (frees disk; the piece drops back to 'written' when nothing rendered is left)."""
    from app import jobs
    with connect() as conn:
        row = conn.execute("SELECT * FROM renders WHERE id = ?", (render_id,)).fetchone()
    if row is None:
        raise UserError("This render no longer exists.", f"render id {render_id}")
    jobs.ensure_idle(row["project_id"])
    with connect() as conn:
        conn.execute("DELETE FROM renders WHERE id = ?", (render_id,))
        if not conn.execute("SELECT 1 FROM renders WHERE piece_id = ?", (row["piece_id"],)).fetchone():
            conn.execute("UPDATE content_pieces SET status = 'written' WHERE id = ? AND status IN ('ready', 'approved')",
                         (row["piece_id"],))
    (config.MEDIA_DIR / row["local_path"]).unlink(missing_ok=True)
    return {"deleted": render_id}


def list_(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT r.id, r.piece_id, r.kind, r.local_path, r.duration, r.fps, r.width, r.height, "
                            "r.created_at, c.idx FROM renders r JOIN content_pieces c ON c.id = r.piece_id "
                            "WHERE r.project_id = ? ORDER BY c.idx, r.kind", (project_id,)).fetchall()
    return [dict(r) for r in rows]
