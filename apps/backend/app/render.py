"""Renderers (PRD §32-34). FFmpeg runs as a subprocess with argument arrays (never shell strings).

Video: 1080x1920 H.264 + AAC, source FPS preserved (§19), narration mixed over optional user-supplied music (§31).
Images: 1080x1350 JPEG, rendered with PIL (better typography: variable font weight, exact wrapping).
Text placement follows the M4 analysis (§26): subject left -> text right, subject right -> text left, center -> lower
block, over a subtle scrim built from the piece palette (§27). Quote lines are wrapped with the bundled Sora font.
"""
import json
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app import config
from app.errors import UserError

FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Sora-Variable.ttf"
VIDEO_W, VIDEO_H = 1080, 1920
IMAGE_W, IMAGE_H = 1080, 1350
MARGIN = 96
SIZES = (96, 84, 72, 64, 56)  # §25: size follows quote length and line count
STALL_SECS = 180  # no ffmpeg progress for this long = wedged; real renders emit progress ~2x/sec


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


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:")


def _probe(path: Path) -> dict:
    proc = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
                           str(path)], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise UserError("The rendered file could not be read back.", proc.stderr[-500:])
    return json.loads(proc.stdout)


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
    if problems:
        raise UserError("The rendered video failed its quality check.", "; ".join(problems))
    return {"duration": float(d["format"]["duration"]), "fps": fps}


def thumbnail(src: Path, out: Path, at: float = 0.5) -> Path:
    """Grab one frame as the cover/thumbnail (PRD §47/§71). ffmpeg argv array, same controls as render_video."""
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["ffmpeg", "-y", "-nostdin", "-nostats", "-hide_banner", "-ss", f"{at}", "-i", str(src),
                           "-frames:v", "1", "-q:v", "3", str(out)], capture_output=True, timeout=60)
    if proc.returncode != 0 or not out.exists():
        raise UserError("Could not grab a cover frame for the export.", proc.stderr.decode("utf-8", "replace")[-400:])
    return out


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
                     scrim_png: Path | None = None, quote: str | None = None, palette: dict | None = None) -> dict:
        """Renders the narration over the visual. `scrim_png`/`quote`/`palette` are optional: omit them for a
        clean video with no text overlay (the Create page's videos). `out_fps` forces 30/60 output."""
        from app.tts import AudioResult
        audio = AudioResult(narration)
        duration = round(audio.duration + 0.6, 3)
        out.parent.mkdir(parents=True, exist_ok=True)
        fps = out_fps or (60.0 if still else (src_fps or 30.0))

        args = ["ffmpeg", "-y", "-nostdin", "-nostats", "-progress", "pipe:1", "-hide_banner"]
        if still:  # §66: slow push-in on stills, at the output frame rate
            frames = round(duration * fps)
            vf = (f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},"
                  f"zoompan=z='min(1+0.06*on/{frames},1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                  f":d=1:s={self.w}x{self.h}:fps={fps:g}")
            args += ["-loop", "1", "-i", str(src)]
        else:
            vf = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h}"
            if src_duration > duration + 2:  # §65 ponytail: take the middle of the clip; motion-scored
                args += ["-ss", f"{round((src_duration - duration) / 2, 3)}"]  # segment scoring needs M5 frame work
            elif src_duration < duration + 1:
                args += ["-stream_loop", "-1"]
            args += ["-i", str(src)]

        narr_idx = 1
        if scrim_png is not None:
            args += ["-i", str(scrim_png)]
            narr_idx = 2
        args += ["-i", str(narration)]

        chain = [f"[0:v]{vf},fps={fps:g}[base]"]
        prev = "base"
        if scrim_png is not None:
            chain += ["[1:v]format=rgba[scr]", "[base][scr]overlay=0:0[o0]"]
            prev = "o0"
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
        chain.append(f"[{prev}]format=yuv420p[vout]")

        a_chain = f"[{narr_idx}:a]loudnorm=I=-16:TP=-1.5:LRA=11[na]"
        if self.music and self.music.exists():
            a_chain += (f";[{narr_idx + 1}:a]volume={self.music_volume},afade=t=in:st=0:d=1,"
                        f"afade=t=out:st={max(duration - 1.5, 0):.3f}:d=1.5[mu]"
                        ";[na][mu]amix=inputs=2:duration=first:normalize=0[aout]")
            args += ["-i", str(self.music)]
        else:
            a_chain += ";[na]anull[aout]"

        args += ["-filter_complex", ";".join(chain) + ";" + a_chain, "-map", "[vout]", "-map", "[aout]",
                 "-c:v", "libx264", "-crf", str(self.crf), "-preset", "veryfast", "-c:a", "aac",
                 "-b:a", self.audio_bitrate, "-movflags", "+faststart", "-t", f"{duration}", str(out)]

        # §32 control: stderr goes to a temp file, never a pipe - a stderr pipe here deadlocks or makes
        # ffmpeg exit 1 mid-teardown (bisected 2026-09-20); -nostdin because ffmpeg otherwise polls the
        # inherited Electron stdin pipe and can hang forever after finishing its encode (same bisect);
        # a watchdog kills a wedged ffmpeg for good either way.
        stalled = threading.Event()
        with tempfile.TemporaryFile() as errf:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL,
                                    text=True, encoding="utf-8")
            watchdog = threading.Timer(STALL_SECS, lambda: (stalled.set(), proc.kill()))
            watchdog.start()
            for line in proc.stdout:  # §32: ffmpeg's own progress, forwarded as report(0..1 within this piece)
                watchdog.cancel()
                watchdog = threading.Timer(STALL_SECS, lambda: (stalled.set(), proc.kill()))
                watchdog.start()
                if line.startswith("out_time_us=") and progress:
                    try:
                        progress(min(float(line.split("=")[1]) / 1e6 / duration, 1.0))
                    except ValueError:
                        pass
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
        return validate_video(out, {"fps": fps, "duration": duration}, self.w, self.h)

    def render_image(self, *, src: Path, out: Path, quote: str, subject_position: str, palette: dict) -> None:
        with Image.open(src) as img:
            img = img.convert("RGB")
            scale = max(IMAGE_H / img.height, IMAGE_W / img.width)
            rw, rh = round(img.width * scale), round(img.height * scale)
            img = img.resize((rw, rh))
            overflow = max(rw - IMAGE_W, 0)  # §21/§26: crop keeps the subject side, centres stay centred
            x0 = {"left": 0, "right": overflow, "center": overflow // 2}[subject_position]
            img = img.crop((x0, (rh - IMAGE_H) // 2, x0 + IMAGE_W, (rh - IMAGE_H) // 2 + IMAGE_H))

        where = placement(quote, subject_position, "image")
        scrim_img = Image.new("RGBA", (IMAGE_W, IMAGE_H))
        a0, a1 = 20, 170
        grad = Image.new("RGBA", (1, IMAGE_H))
        dr, dg, db = (int(palette["overlay"][i:i + 2], 16) for i in (1, 3, 5))
        grad.putdata([(dr, dg, db, round(a0 + (a1 - a0) * y / (IMAGE_H - 1))) for y in range(IMAGE_H)])
        scrim_img.paste(grad.resize((IMAGE_W, IMAGE_H)), (0, 0))
        img = Image.alpha_composite(img.convert("RGBA"), scrim_img)

        draw = ImageDraw.Draw(img)
        font = _font(where["size"])
        for (x, y), line in zip(where["positions"], where["lines"]):
            draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 115))  # soft shadow
            draw.text((x, y), line, font=font, fill=palette["text"])
        out.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(out, "JPEG", quality=90)
        validate_image(out)
