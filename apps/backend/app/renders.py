"""Render orchestration (PRD §33): narration per piece, then video/image outputs, validated and recorded.

Rides the shared job system (generation_jobs.kind = 'render'); piece status walks written -> rendering -> ready.
"""
import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from app import config, content, design, edit, motion, music, projects, render, reveal, settings, tts
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


VOICED_HOLD = 10.0  # seconds: a voiced quote video never runs shorter; longer quotes run as long as they're read


def _wanted_kinds(brief: dict, piece: dict) -> list[str]:
    """video_image renders both; explicit format forces one; otherwise the plan's preferred type.
    Instagram Feed is a 4:5 image post (PRD §72), so targeting it always renders the image as well."""
    if brief["format"] == "image_voiced":  # the picture first: the video is made from it
        return ["image", "video"]
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
            tmp = config.MEDIA_DIR / "tmp"
            tmp.mkdir(parents=True, exist_ok=True)
            # a folder per call: two projects rendering at once shared tmp/narration and read each other's audio
            with tempfile.TemporaryDirectory(dir=tmp) as work:
                return transcribe(audio, Path(work))["words"]
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
        if still and (a["width"] or 0) > (a["height"] or 1) * 0.75:
            shot["blur"] = True  # an archival painting or map: shown whole over a blurred fill of itself
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
    voice = (voice if voice in tts.VOICES or voice in tts.NARRATORS
             else tts.GENRE_VOICES.get(brief.get("tone"), tts.DEFAULT_VOICE))

    n = len(pieces)
    fail = getattr(report, "fail", None)  # jobs.py's report can mark one step failed and carry on
    for i, piece in enumerate(pieces, 1):
        content_data = piece["content"]
        kinds = _wanted_kinds(brief, piece)
        voiced = brief["format"] == "image_voiced"

        def at(step: str, f: float, i=i, piece=piece) -> None:
            # "Piece 3 (2 of 5): Encoding video": the piece number matches the list, the count shows the way left
            report(f"Piece {piece['idx']} ({i} of {n}): {step}", (i - 1 + min(max(f, 0.0), 1.0)) / n)

        # each piece's share of the bar: narration and word timings first, ffmpeg's encode is the long part
        enc = (0.45, 0.95 if "image" in kinds else 1.0) if "video" in kinds else None
        if not s["music_path"]:  # the bundled library (owner 2026-11-10): a genre track, varied piece to piece
            renderer.music = music.pick(brief.get("tone", ""), piece["idx"]) if s.get("bundled_music", True) else None
            renderer.music_volume = music.VOLUME
        try:
            narration = None
            if "video" in kinds:  # a quote image has no voice: never pay for (or wait on) narration it won't use
                at("Narrating", 0.0)
                if voiced:  # "Seneca once wrote", the quote, the book, then the lesson on that exact quote
                    lesson = content_data.get("lesson") or ""
                    script, parts = reveal.script(content_data["quote"], lesson)
                    narration = asyncio.run(engine.generate(
                        script, voice, "the opening words said quietly, then the quote read slowly so each phrase "
                        "lands, a breath of silence between its sentences and before the book's name"
                        + ("; then, after a pause, the lesson spoken warmly and personally to one listener, like "
                           "advice from someone who has lived it" if lesson else "")))
                else:
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
                    if kind == "video" and voiced:
                        # the photo, dimmed, with the quote revealed 2-3 words at a time as it is read (reveal.py);
                        # then the quote picture just rendered, over a blurred fill of itself, for the book and the
                        # lesson. At least VOICED_HOLD seconds so a short quote still gets a moment on screen.
                        at("Timing the words", 0.25)
                        words = _words(script, narration.path, narration.duration)
                        times = reveal.timeline(script, words, narration.duration)
                        times = reveal.stretch(narration.path, parts, times)  # pauses for the reveal
                        narration = tts.AudioResult(narration.path)
                        ass_text, post_at = reveal.ass(parts, times, renderer.w, renderer.h)
                        subs = config.MEDIA_DIR / "tmp" / f"{piece['id']}-subs.ass"
                        subs.parent.mkdir(parents=True, exist_ok=True)
                        subs.write_text(ass_text, encoding="utf-8")
                        total = round(max(narration.duration + 0.6, VOICED_HOLD), 3)  # render_video's own length
                        kb = brief.get("ken_burns", True)  # briefs saved before the toggle keep the move
                        fade = 0.8
                        first = min(post_at + fade / 2, total - 1.0)
                        if len(pool) > 1 or asset["asset_type"] == "video":  # clips behind the words
                            shots = _behind_words(pool, first, kb, piece["idx"])
                            dim = Path(shots[0]["src"])
                        else:
                            dim = _dimmed(asset, config.MEDIA_DIR / "tmp" / f"{piece['id']}-dim.jpg")
                            shots = [{"src": str(dim), "length": first, "still": True,
                                      "motion": "drift" if kb else "none"}]
                        shots += [{"src": str(full_out.with_name(f"{piece['idx']:03d}-image.jpg")), "still": True,
                                  "length": total - first + fade, "blur": True, "motion": "push" if kb else "none",
                                  "transition": "fade", "tdur": fade}]
                        at("Encoding video", enc[0])
                        info = renderer.render_video(src=dim, narration=narration.path, out=full_out,
                                                     subject_position="center", src_fps=0, src_duration=0, still=True,
                                                     progress=lambda f: at("Encoding video", enc[0] + f * (enc[1] - enc[0])),
                                                     out_fps=brief["fps"], hold=VOICED_HOLD, shots=shots,
                                                     subtitles=subs)
                        duration, fps, w, h = info["duration"], info["fps"], renderer.w, renderer.h
                    elif kind == "video":
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
            from app.jobs import UNSTICK
            with connect() as conn:
                conn.execute(UNSTICK + " WHERE id = ? AND status = 'rendering'", (piece["id"],))
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
        finally:  # the voice track and the frame/subtitle scratch are baked into the render now: never kept
            if narration is not None:
                Path(narration.path).unlink(missing_ok=True)
            for scratch in (f"{piece['id']}-frame.jpg", f"{piece['id']}-subs.ass", f"{piece['id']}-dim.jpg"):
                (config.MEDIA_DIR / "tmp" / scratch).unlink(missing_ok=True)
    report("Done", 1.0)


# seconds per clip behind a voiced quote (owner 2026-11-12: "a range, not a static amount"): each slot is drawn
# from this range, so one runs 2.5 s, the next 3.2, then 3.8, then 2.0; ~2.9 s on average, calm but never metronomic
CLIP_RANGE = (2.0, 3.8)
CLIP_JOIN = 0.5   # cross-dissolve between those clips
CLIP_MIN = 1.2    # the shortest slot: more picked clips than ~2.5 s slots means quicker cuts, never a dropped clip


def _slots(n: int, total: float, seed: int) -> list[float]:
    """n slot lengths drawn from CLIP_RANGE, scaled to sum to `total`. Seeded (the piece number), so a re-render
    keeps its cut; a slot squeezed under CLIP_MIN by the scaling evens the set out until none is."""
    import random
    rng = random.Random(seed)
    raw = [rng.uniform(*CLIP_RANGE) for _ in range(n)]
    even = total / n
    lengths = [r * total / sum(raw) for r in raw]
    while min(lengths) < CLIP_MIN and even >= CLIP_MIN:
        lengths = [(x + even) / 2 for x in lengths]
    return lengths


def _behind_words(pool: list[dict], span: float, ken_burns: bool, seed: int = 0) -> list[dict]:
    """The voiced quote's reveal over footage (owner 2026-11-12): the picked clips (and any photos) cut together
    across `span` seconds, a cut every 2-3.8 s (CLIP_RANGE, varied slot to slot), dissolved, dimmed for the words. A clip enters at its middle
    and loops only if it is shorter than its slot; a set too small for the span comes round again. Every clip only
    lends a slice (owner 2026-11-12: "not the entire length"), so a long video never plays out and the cuts keep the
    hook; a set larger than the slots shortens them (down to CLIP_MIN) so every picked clip is seen."""
    n = max(1, round(span / (sum(CLIP_RANGE) / 2)), min(len(pool), int(span // CLIP_MIN)))
    # every dissolve eats CLIP_JOIN from the running total, so the slots together run that much longer
    lengths = _slots(n, span + (n - 1) * CLIP_JOIN, seed)
    moves = ["in", "out", "pan"] if ken_burns else [None]
    shots = []
    for i, each in enumerate(lengths):
        a = pool[i % len(pool)]
        src = str(config.MEDIA_DIR / a["local_path"])
        if a["asset_type"] == "image":
            shot = {"src": src, "length": each, "still": True, "motion": "drift" if ken_burns else "none"}
        else:
            avail = max(a["duration"] or each, 0.5)
            lap = i // len(pool)  # a second time round enters further in, so a repeat is a new moment
            seek = max((avail - each) * (0.5 + 0.25 * (lap % 2)), 0.0) if avail > each else 0.0
            shot = {"src": src, "length": each, "still": False, "seek": round(seek, 2), "loop": avail < each + seek,
                    "motion": moves[i % len(moves)]}
        shot["dim"] = True
        if i:
            shot["transition"], shot["tdur"] = "fade", CLIP_JOIN
        shots.append(shot)
    return shots


def _dimmed(asset: dict, out: Path) -> Path:
    """The piece's photo, darkened and softened so white words read on it anywhere, a busy texture included (a
    video asset gives its middle frame)."""
    from PIL import Image, ImageEnhance, ImageFilter
    src = config.MEDIA_DIR / asset["local_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    if asset["asset_type"] == "video":
        render.thumbnail(src, out, at=max((asset["duration"] or 0) / 2, 0.5))
        src = out
    with Image.open(src) as im:
        rgb = im.convert("RGB")
        dark = ImageEnhance.Brightness(rgb.filter(ImageFilter.GaussianBlur(rgb.width / 300))).enhance(0.4)
    dark.save(out, quality=92)
    return out


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
