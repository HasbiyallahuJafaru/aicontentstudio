"""Renderers (PRD §32-34). FFmpeg runs as a subprocess with argument arrays (never shell strings).

Video: 1080x1920 H.264 + AAC, source FPS preserved (§19), narration mixed over optional user-supplied music (§31).
Images: 1080x1350 JPEG, art-directed designs drawn with PIL (app/design.py).
Text placement follows the M4 analysis (§26): subject left -> text right, subject right -> text left, center -> lower
block, over a subtle scrim built from the piece palette (§27). Quote lines are wrapped with the bundled Sora font.
"""
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app import config, design, edit, motion
from app.errors import UserError

FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Sora-Variable.ttf"
VIDEO_W, VIDEO_H = 1080, 1920
IMAGE_W, IMAGE_H = 1080, 1350
MARGIN = 96
SIZES = (96, 84, 72, 64, 56)  # §25: size follows quote length and line count
STALL_SECS = 180  # no ffmpeg progress for this long = wedged; real renders emit progress ~2x/sec
SUBTITLES_FONTS = design.FONTS_DIR
# Shot matching (owner 2026-11-10: "no colour grading so everything matches"): per-channel level stretch, half
# strength and temporally smoothed, so each source reaches a common exposure and a near-neutral white balance before
# the genre grade. ponytail: levels only, not a learned colour transfer; enough to stop one clip reading orange and
# the next blue under the same grade.
SHARPEN = 0.45  # unsharp luma amount for every finished render (0.6+ starts to halo around type)
NORMALIZE = "normalize=smoothing=24:independence=0.6:strength=0.45"  # every bundled face, so any caption font resolves


def _font(size: int, weight: int = 600) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_PATH), size)
    try:
        f.set_variation_by_axes([weight])
    except OSError:
        pass  # ponytail: non-variable fallback renders at regular weight
    return f


def font_size(quote: str, max_lines: int, w: int = VIDEO_W) -> tuple[int, list[str]]:
    """Largest size whose wrapped block stays within margins and the line budget; scales with the canvas."""
    margin = round(MARGIN * w / VIDEO_W)
    for size in SIZES:
        s = round(size * w / VIDEO_W)
        font = _font(s)
        lines = wrap(quote, font, w - 2 * margin)
        if len(lines) <= max_lines:
            return s, lines
    s = round(SIZES[-1] * w / VIDEO_W)
    return s, wrap(quote, _font(s), w - 2 * margin)


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if font.getlength(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def placement(quote: str, subject_position: str, kind: str, w: int = VIDEO_W, h: int = VIDEO_H) -> dict:
    """§26: avoid the subject; keep the block off the subject side, centered work goes lower."""
    size, lines = font_size(quote, max_lines=5 if kind == "video" else 6, w=w)
    font = _font(size)
    line_h = round(size * 1.24)
    height = line_h * len(lines)
    margin = round(MARGIN * w / VIDEO_W)
    if subject_position == "left":
        mode, base_x = "right", w - margin
    elif subject_position == "right":
        mode, base_x = "left", margin
    else:
        mode, base_x = "center", w // 2
    y0 = (h - height) // 2 if kind == "video" else round(h * 0.58) - height // 2
    positions = []
    for i, line in enumerate(lines):
        lw = font.getlength(line)
        x = {"right": base_x - lw, "center": base_x - lw / 2, "left": base_x}[mode]
        positions.append((round(x), y0 + i * line_h))
    return {"size": size, "lines": lines, "positions": positions}


def scrim(path: Path, hex_color: str, w: int, h: int, strength: tuple[int, int]) -> Path:
    """§27: a subtle vertical gradient overlay in the palette's dark tone (top alpha -> bottom alpha)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    img = Image.new("RGBA", (1, h))
    a0, a1 = strength
    img.putdata([(r, g, b, round(a0 + (a1 - a0) * y / (h - 1))) for y in range(h)])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((w, h)).save(path)
    return path


# what every platform-bound encode carries: a peak-bitrate cap (film grain pushed crf-only renders to 25-50 Mbps,
# over Instagram's limit), BT.709 limited-range tags (untagged video gets colour-shifted on re-encode) and a
# keyframe every 2 s. Shared with the clip renderer.
DELIVERY = ("-maxrate", "12M", "-bufsize", "24M", "-force_key_frames", "expr:gte(t,n_forced*2)",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709")


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:")


def _probe(path: Path) -> dict:
    proc = subprocess.run([config.FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
                           str(path)], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise UserError("The rendered file could not be read back.", proc.stderr[-500:])
    return json.loads(proc.stdout)


def open_luma(path: Path) -> float:
    """Average brightness of the first frame, 0..1. The hook lives in the first seconds; opening on black
    throws them away, so a render that starts dark is a defect, not a style."""
    proc = subprocess.run([config.FFMPEG, "-nostdin", "-v", "error", "-i", str(path), "-frames:v", "1",
                           "-vf", "scale=32:32,format=gray", "-f", "rawvideo", "-"],
                          capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    return sum(proc.stdout) / len(proc.stdout) / 255 if proc.stdout else 1.0


def audio_misstamped(path: Path) -> int:
    """AAC packets (all but the last) whose timestamps don't advance one full 1024-sample frame. loudnorm used
    to squeeze the opening ~0.6 s together then jump to 3 s; local players don't care, but every platform's
    transcoder obeys the stamps and the posted video speeds up or drags for its first seconds (2026-11-09)."""
    proc = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "packet=duration",
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=60)
    durs = [line.strip().rstrip(",") for line in proc.stdout.splitlines() if line.strip()]
    return sum(d != "1024" for d in durs[:-1])


def validate_video(path: Path, want: dict, w: int, h: int) -> dict:
    """§34: resolution, orientation, codec, fps and duration are checked before anything is accepted."""
    d = _probe(path)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    fps = eval(v.get("r_frame_rate", "0/1"))  # noqa: S307 - "num/den" from ffprobe, not user input
    problems = []
    if (v.get("width"), v.get("height")) != (w, h):
        problems.append(f"resolution is {v.get('width')}x{v.get('height')}, wanted {w}x{h}")
    if v.get("codec_name") != "h264":
        problems.append(f"video codec is {v.get('codec_name')}, wanted h264")
    if a is None or a.get("codec_name") != "aac":
        problems.append("audio track is missing or not AAC")
    if abs(fps - want["fps"]) > 1.5:
        problems.append(f"fps is {fps:.2f}, wanted {want['fps']:.2f}")
    if abs(float(d["format"]["duration"]) - want["duration"]) > 1.5:
        problems.append(f"duration is {float(d['format']['duration']):.2f}s, wanted ~{want['duration']:.2f}s")
    # the container reports its longest stream, so a picture that ran short (shots re-timed by the wrong frame
    # rate, 2026-11-09) hid behind the audio: each stream has to fill the timeline on its own
    for kind, stream in (("picture", v), ("sound", a)):
        if stream and stream.get("duration") and abs(float(stream["duration"]) - want["duration"]) > 0.25:
            problems.append(f"the {kind} runs {float(stream['duration']):.2f}s, wanted {want['duration']:.2f}s")
    if v.get("pix_fmt") != "yuv420p" or v.get("color_range") not in (None, "tv"):
        problems.append(f"picture format is {v.get('pix_fmt')}/{v.get('color_range')}, wanted yuv420p limited range")
    if a is not None and audio_misstamped(path):
        problems.append("the audio timestamps are uneven, so platforms would warp the opening")
    if open_luma(path) < 0.02:
        problems.append("the video opens on a black frame, so the hook is wasted")
    if problems:
        raise UserError("The rendered video failed its quality check.", "; ".join(problems))
    return {"duration": float(d["format"]["duration"]), "fps": fps}


def thumbnail(src: Path, out: Path, at: float = 0.5) -> Path:
    """Grab one frame as the cover/thumbnail (PRD §47/§71). ffmpeg argv array, same controls as render_video.
    If `at` sits past the end of a shorter-than-reported file, it retries once from 0."""
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = None
    for seek in (at, 0):
        proc = subprocess.run([config.FFMPEG, "-y", "-nostdin", "-nostats", "-hide_banner", "-ss", f"{seek}",
                               "-i", str(src), "-frames:v", "1", "-q:v", "3", str(out)],
                              capture_output=True, timeout=60)
        if proc.returncode == 0 and out.exists():
            return out
    raise UserError("Could not grab a cover frame for the export.",
                    proc.stderr.decode("utf-8", "replace")[-400:])


def validate_image(path: Path) -> None:
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        if img.size != (IMAGE_W, IMAGE_H) or img.format != "JPEG":
            raise UserError("The rendered image failed its quality check.",
                            f"{img.size} {img.format}, wanted {IMAGE_W}x{IMAGE_H} JPEG")


class FFmpegRenderer:
    def __init__(self, crf: int, audio_bitrate: str, music: Path | None, music_volume: float,
                 w: int = VIDEO_W, h: int = VIDEO_H):
        self.crf, self.audio_bitrate = crf, audio_bitrate
        self.music, self.music_volume = music, music_volume
        self.w, self.h = w, h
        if not Path(FONT_PATH).exists():
            raise UserError("The Sora font is missing from the backend assets.", str(FONT_PATH))

    def render_video(self, *, src: Path, narration: Path, out: Path, subject_position: str, src_fps: float,
                     src_duration: float, still: bool, progress, out_fps: float | None = None,
                     scrim_png: Path | None = None, quote: str | None = None, palette: dict | None = None,
                     look: str = "none", duck: float = 6.0, blur_background: bool = False, parallax: bool = False,
                     hold: float = 0.0,
                     subtitles: Path | None = None, shots: list[dict] | None = None,
                     layers: list[dict] | None = None) -> dict:
        """Edits a finished video the way the top motivational studios do: the footage is cut into motion shots
        (zoom in / zoom out / pan / push-in), a still cutaway can be merged between video shots, the whole
        timeline is graded with the look preset and dressed with vignette + film grain, narration is normalised
        and optional karaoke subtitles are burned.

        `shots` (optional) describes the cut: [{src, seek, length, still, motion, blur}] — renders.py builds it
        from the piece's asset pool. Without it a single shot is synthesised from `src` (old behaviour)."""
        from app.tts import AudioResult
        audio = AudioResult(narration)
        duration = round(max(audio.duration + 0.6, hold), 3)  # `hold`: the shortest the video may run
        out.parent.mkdir(parents=True, exist_ok=True)
        fps = out_fps or (30.0 if still else (src_fps or 30.0))

        if not shots:
            seek = round(max((src_duration - duration) / 2, 0), 3) if src_duration > duration + 2 else 0.0
            move = "push" if (still or parallax) else None
            shots = [{"src": str(src), "seek": seek, "length": duration, "still": still, "motion": move,
                      "blur": blur_background}]

        # each shot's camera move is `move`: a local named `motion` shadowed the motion module and crashed every
        # render with animated titles on (2026-11-07)
        out, narration, run_dir = Path(out).resolve(), Path(narration).resolve(), None
        # encode beside the old render and swap only after the check passes: a cancelled or failed re-render
        # used to leave a 'ready' piece pointing at a truncated file, which then got posted
        final, out = out, out.with_suffix(".part.mp4")
        args = [config.FFMPEG, "-y", "-nostdin", "-nostats", "-progress", "pipe:1", "-hide_banner"]
        chain = []
        for i, shot in enumerate(shots):
            length = max(shot["length"], 0.4)
            # a ramped shot plays slower, so it needs less source; stills and the blur treatment never ramp
            speed = 1.0 if shot.get("still") or shot.get("blur") else float(shot.get("speed", 1.0))
            if shot.get("still"):
                args += ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{length:.3f}", "-i", str(shot["src"])]
                move = shot.get("motion") or "push"
            else:
                if shot.get("loop"):  # shorter than the edit: loop the source instead of running out mid-shot
                    args += ["-stream_loop", "-1"]
                if shot.get("seek"):
                    args += ["-ss", f"{shot['seek']:.3f}"]
                args += ["-t", f"{length / speed:.3f}", "-i", str(shot["src"])]
                move = shot.get("motion")
            frames = max(round(length * fps), 1)
            ramp = f",setpts={speed:g}*PTS" if speed != 1.0 else ""
            if shot.get("blur"):
                # a still (archival painting, map) is composed at 2x and pushed in slowly, so it moves like the
                # rest of the edit instead of freezing; a video keeps the plain fit
                k = 2 if shot.get("still") else 1
                bw, bh = k * self.w, k * self.h
                push = (f",zoompan=z='min(1+0.05*on/{frames:g},1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                        f":d=1:s={self.w}x{self.h}:fps={fps:g}") if k == 2 and shot.get("motion") != "none" else ""
                chain.append(f"[{i}:v]{NORMALIZE},split=2[bg{i}][fg{i}];"
                             f"[bg{i}]scale={bw // 4}:{bh // 4}:force_original_aspect_ratio=increase,"
                             f"crop={bw // 4}:{bh // 4},boxblur=12:2,scale={bw}:{bh}[bgb{i}];"
                             f"[fg{i}]scale={bw}:{bh}:force_original_aspect_ratio=decrease:flags=lanczos[fgp{i}];"
                             f"[bgb{i}][fgp{i}]overlay=(W-w)/2:(H-h)/2,fps={fps:g}{push},setsar=1[v{i}]")
                continue
            # zoompan quantises its zoom in source pixels, which stair-steps on a still: supersample first
            box = (2 * self.w, 2 * self.h) if shot.get("still") else (self.w, self.h)
            # lanczos: the sharpest of ffmpeg's resamplers (the default bicubic softens every upscale)
            geom = f"scale={box[0]}:{box[1]}:force_original_aspect_ratio=increase:flags=lanczos,crop={box[0]}:{box[1]}"
            zoom = {"push": f",zoompan=z='min(1+0.06*on/{frames:g},1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                            f":d=1:s={self.w}x{self.h}:fps={fps:g}",
                    "slow": f",zoompan=z='min(1+0.03*on/{frames:g},1.03)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                            f":d=1:s={self.w}x{self.h}:fps={fps:g}",
                    "in": f",zoompan=z='min(1+0.08*on/{frames:g},1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                          f":d=1:s={self.w}x{self.h}:fps={fps:g}",
                    "out": f",zoompan=z='max(1.08-0.08*on/{frames:g},1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                           f":d=1:s={self.w}x{self.h}:fps={fps:g}",
                    "pan": f",zoompan=z='1.1':x='(iw-iw/zoom)*on/{frames:g}':y='ih/2-(ih/zoom/2)'"
                           f":d=1:s={self.w}x{self.h}:fps={fps:g}",
                    # Ken Burns (voiced quote videos, 2026-11-12): a slow push that also drifts sideways
                    "drift": f",zoompan=z='min(1+0.12*on/{frames:g},1.12)':x='(iw-iw/zoom)*(0.3+0.4*on/{frames:g})'"
                             f":y='(ih-ih/zoom)*0.45':d=1:s={self.w}x{self.h}:fps={fps:g}"}.get(move, "")
            if not zoom:  # a locked-off shot still has to land on the canvas at the timeline's frame rate
                zoom = f",scale={self.w}:{self.h},fps={fps:g}"
            # conform to the timeline rate BEFORE zoompan: zoompan (d=1) stamps one output frame per input frame
            # at its own rate, so a 25 fps clip played 1.2x fast and 59.94 fps at half speed (2026-11-09). The ramp
            # comes first so fps fills the slow-mo with whole frames instead of leaving a VFR gap.
            # NORMALIZE first, on the 1x frame: every source lands on the same exposure and a neutral white
            # before the shared grade, so clips from different cameras and a scanned painting cut as one film
            # (a still is matched on its source frame, before the 2x supersample, to keep the cost down)
            order = f"{NORMALIZE},{geom}" if shot.get("still") else f"{geom},{NORMALIZE}"
            # dim: footage under words (voiced quote clips, 2026-11-12), a touch darker so small white type reads;
            # never blurred (the owner's references keep the footage natural and sharp)
            # `dim` is the brightness kept (renders.DIM for a darker clip, 1.0 for a bright one; True = 0.8)
            k = 0.8 if shot.get("dim") is True else float(shot.get("dim") or 1.0)
            dim = f",colorchannelmixer=rr={k:g}:gg={k:g}:bb={k:g}" if k < 1.0 else ""
            chain.append(f"[{i}:v]{order}{ramp},fps={fps:g}{zoom}{dim},setsar=1[v{i}]")

        # every join is an xfade, a hard cut included (one frame): one timeline, one set of offset maths.
        # xfade eats `duration` seconds at each join, which the planned shot lengths already carry back.
        if len(shots) > 1:
            prev, acc = "v0", max(shots[0]["length"], 0.4)
            for i in range(1, len(shots)):
                tr, td = shots[i].get("transition", "fade"), float(shots[i].get("tdur", 0.04))
                chain.append(f"[{prev}][v{i}]xfade=transition={tr}:duration={td:g}"
                             f":offset={max(acc - td, 0):.3f}[x{i}]")
                prev, acc = f"x{i}", acc + max(shots[i]["length"], 0.4) - td
            chain.append(f"[{prev}]null[vc]")
        else:
            chain.append("[v0]null[vc]")

        # grade, then halation, then the dressing that sells it as film
        style = edit.LOOKS.get(look, edit.LOOKS["none"])
        prev = "vc"
        if style["grade"]:
            chain.append(f"[{prev}]{style['grade']}[graded]")
            prev = "graded"
        if style["bloom"]:
            chain.append(f"[{prev}]split=2[base][hi];[hi]gblur=sigma=18,curves=all='0/0 0.62/0.12 1/1'[blur];"
                         f"[base][blur]blend=all_mode=screen:all_opacity={style['bloom']:g}[bloomed]")
            prev = "bloomed"
        # a light luma sharpen on every render (2026-11-12, "not sharp once uploaded"): platform re-encodes soften
        # fine detail, so the master leaves a little crisper than it looks right; a look's own unsharp overrides
        dress = [f"unsharp=5:5:{style['unsharp'] or SHARPEN:g}:5:5:0"]
        if style["vignette"]:
            dress.append(f"vignette=angle=PI/{style['vignette']:g}")
        if style["grain"]:
            dress.append(f"noise=alls={style['grain']}:allf=t+u")
        if style["bars"]:
            dress.append(f"drawbox=x=0:y=0:w=iw:h=ih*{style['bars']:g}:color=black@1:t=fill")
            dress.append(f"drawbox=x=0:y=ih*{1 - style['bars']:g}:w=iw:h=ih*{style['bars']:g}:color=black@1:t=fill")
        chain.append(f"[{prev}]{','.join(dress) or 'null'}[film]")
        prev = "film"
        if subtitles is not None:  # burned subtitles in the brief's caption style
            # run from the subtitle's folder with relative names: an apostrophe in an absolute path (a Windows
            # username like O'Brien) can't be quoted inside the filter graph. Every input path is absolute.
            run_dir = subtitles.parent
            try:
                fonts_dir = Path(os.path.relpath(SUBTITLES_FONTS, run_dir)).as_posix()
            except ValueError:  # fonts on another drive: no relative path exists
                fonts_dir = esc(str(SUBTITLES_FONTS).replace("\\", "/"))
            chain.append(f"[{prev}]ass='{esc(subtitles.name)}':fontsdir='{fonts_dir}'[sub]")
            prev = "sub"
        narr_idx = len(shots)
        if scrim_png is not None:
            args += ["-i", str(scrim_png)]
            chain += [f"[{narr_idx}:v]format=rgba[scr]", f"[{prev}][scr]overlay=0:0[o0]"]
            prev = "o0"
            narr_idx += 1
        if layers:  # animated hook title / callouts (app/motion.py), over the subtitles
            motion_args, motion_chain, prev = motion.overlay_graph(prev, layers, narr_idx)
            args += motion_args
            chain += motion_chain
            narr_idx += len(layers)
        args += ["-i", str(narration)]
        if quote:
            where = placement(quote, subject_position, "video", self.w, self.h)
            # §32 ponytail: the drive-letter colon needs graph quoting AND escaping: fontfile='C\:/...'
            font_file = esc(str(FONT_PATH).replace("\\", "/"))
            for i, (x, y) in enumerate(where["positions"]):
                text = where["lines"][i].replace("'", "\u2019")  # typographic apostrophes read better and skip escaping
                dt = (f"drawtext=fontfile='{font_file}':text={esc(text)}:fontcolor={(palette or {}).get('text', '#FFFFFF')}"
                      f":fontsize={where['size']}:x={x}:y={y}:line_spacing=0"
                      ":shadowcolor=black@0.45:shadowx=0:shadowy=3:expansion=none")
                nxt = f"t{i + 1}"
                chain.append(f"[{prev}]{dt}[{nxt}]")
                prev = nxt
        # stills arrive as full-range JPEG (yuvj420p, BT.601): convert so platforms don't crush or wash the blacks
        chain.append(f"[{prev}]scale=out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[vout]")

        a_chain = (f"[{narr_idx}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,asetpts=N/SR/TB,"  # restamp: see render_clip.py
                   f"apad=whole_dur={duration}[na]")  # the sound runs the whole timeline, the 0.6 s tail included
        if self.music and self.music.exists():
            a_chain += (";[na]asplit=2[nk][key]"
                        f";[{narr_idx + 1}:a]volume={self.music_volume},afade=t=in:st=0:d=1,"
                        f"afade=t=out:st={max(duration - 1.5, 0):.3f}:d=1.5[mu]"
                        # a gentle duck: the genre's depth in dB maps to a soft ratio (2026-11-12: ratio = 1.5 x dB
                        # ran 7.5-12 and buried the music under every word); the bed stays audible under the voice
                        f";[mu][key]sidechaincompress=threshold=0.05:ratio={1 + duck / 3:.2f}:knee=4"
                        ":attack=30:release=600[duck]"
                        ";[nk][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[aout]")
            args += ["-stream_loop", "-1", "-i", str(self.music)]  # a short bed loops rather than stopping mid-video
        else:
            a_chain += ";[na]anull[aout]"


        args += ["-filter_complex", ";".join(chain) + ";" + a_chain, "-map", "[vout]", "-map", "[aout]",
                 "-c:v", "libx264", "-crf", str(self.crf), "-preset", "veryfast", "-c:a", "aac",  # CRF sets quality; medium here
                # more than doubles a director-cut render (smoke: >240 s vs 98 s) for mostly a smaller file
                 "-b:a", self.audio_bitrate, *DELIVERY, "-movflags", "+faststart", "-t", f"{duration}", str(out)]

        # §32 control: stderr goes to a temp file, never a pipe - a stderr pipe here deadlocks or makes
        # ffmpeg exit 1 mid-teardown (bisected 2026-09-20); -nostdin because ffmpeg otherwise polls the
        # inherited Electron stdin pipe and can hang forever after finishing its encode (same bisect);
        # a watchdog kills a wedged ffmpeg for good either way.
        stalled = threading.Event()
        with tempfile.TemporaryFile() as errf:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL, cwd=run_dir,
                                    text=True, encoding="utf-8")
            watchdog = threading.Timer(STALL_SECS, lambda: (stalled.set(), proc.kill()))
            watchdog.start()
            try:
                for line in proc.stdout:  # §32: ffmpeg's own progress, forwarded as report(0..1 within this piece)
                    watchdog.cancel()
                    watchdog = threading.Timer(STALL_SECS, lambda: (stalled.set(), proc.kill()))
                    watchdog.start()
                    if line.startswith("out_time_us=") and progress:
                        try:
                            secs = float(line.split("=")[1]) / 1e6
                        except ValueError:  # "N/A" before the first frame
                            continue
                        progress(min(secs / duration, 1.0))
            except BaseException:  # the progress callback raised (the job was cancelled): stop ffmpeg now
                watchdog.cancel()
                proc.kill()
                proc.wait()
                raise
            watchdog.cancel()
            _, _ = proc.communicate()
            if stalled.is_set():
                errf.seek(0)
                tail = errf.read().decode("utf-8", "replace")[-400:]
                raise UserError("FFmpeg stopped responding and was stopped.",
                                f"no progress for {STALL_SECS}s, killed while rendering {out.name}\n{tail}")
            if proc.returncode != 0:
                errf.seek(0)
                raise UserError("FFmpeg failed while rendering the video.",
                                errf.read().decode("utf-8", "replace")[-800:])
        try:
            info = validate_video(out, {"fps": fps, "duration": duration}, self.w, self.h)
        except BaseException:
            out.unlink(missing_ok=True)
            raise
        os.replace(out, final)
        return info

    def render_image(self, *, src: Path | None, out: Path, quote: dict | str, subject_position: str, palette: dict,
                     design_name: str = "arch", face: str = "auto", position: str = "auto") -> None:
        """The 4:5 still, art-directed by `design_name` (app/design.py); `src` None is fine for type-only designs."""
        if isinstance(quote, str):
            quote = {"text": quote}
        photo = None
        if src is not None:
            try:
                photo = Image.open(src)
                photo.load()
            except UnidentifiedImageError as e:
                # videos must be frame-grabbed before they get here (renders.py); anything else is bad source data
                raise UserError("This visual isn't an image the studio can crop.", f"{src} ({e})") from e
        img = design.compose(design_name, photo, quote, palette, IMAGE_W, IMAGE_H, subject=subject_position,
                             face=face, position=position)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(out, "JPEG", quality=92, subsampling=0)  # 4:4:4: fine type stays sharp
        validate_image(out)
