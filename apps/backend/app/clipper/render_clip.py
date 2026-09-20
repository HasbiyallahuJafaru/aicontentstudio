"""Clip render: face-tracked crop, burned karaoke captions and a cover frame, all through our ffmpeg discipline."""
import os
from pathlib import Path

from app.clipper.captions import FONTS, captions
from app.clipper.crop import crop_filter
from app.clipper.ff import ffmpeg

# orientations a clip can take: crop ratio (w, h) and output pixel size
ORIENTATIONS = {"9:16": ((9, 16), (1080, 1920)), "16:9": ((16, 9), (1920, 1080)), "1:1": ((1, 1), (1080, 1080))}


def render(video, start: float, end: float, out: Path, words: list[dict], burn: bool = True,
           orientation: str = "9:16", fps: int | None = None) -> None:
    """Write out (mp4), its .ass captions and a .jpg cover. `burn`: draw the captions into the video (off when the
    source already has its own); the .ass file is written either way. `fps`: force 30/60 output when the brief
    asks for it (the source's own frame rate is kept otherwise)."""
    (rw, rh), (width, height) = ORIENTATIONS[orientation]
    out = out.resolve()
    out.with_suffix(".ass").write_text(captions(words, start, end, width, height), encoding="utf-8")
    # cwd = output dir and relative paths, so filter args carry no Windows drive colons (they break filter parsing)
    fonts = Path(os.path.relpath(FONTS, out.parent)).as_posix()
    burned = f",ass={out.stem}.ass:fontsdir={fonts}" if burn else ""
    ffmpeg("-ss", f"{start:.3f}", "-i", str(video.resolve()), "-t", f"{end - start:.3f}",
           "-vf", f"{crop_filter(video, start, end, (rw, rh))},scale={width}:{height},setsar=1{burned}",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
           *(("-r", str(fps)) if fps else ()),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out.name, cwd=out.parent)
    # cover = frame at 1 s: the speaker already framed
    ffmpeg("-ss", "1", "-i", out.name, "-frames:v", "1", "-q:v", "3", out.with_suffix(".jpg").name, cwd=out.parent)
