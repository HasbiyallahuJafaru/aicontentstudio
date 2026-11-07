"""Clip render: the kept source ranges joined into one clip, each face-tracked, captions retimed and burned, and a
cover frame, all through our ffmpeg discipline."""
import os
from pathlib import Path

from app import motion
from app.clipper.captions import FONTS, captions
from app.clipper.crop import crop_filter
from app.clipper.ff import ffmpeg
from app.clipper.tighten import retime

# orientations a clip can take: crop ratio (w, h) and output pixel size
ORIENTATIONS = {"9:16": ((9, 16), (1080, 1920)), "16:9": ((16, 9), (1920, 1080)), "1:1": ((1, 1), (1080, 1080))}
FADE = 0.01  # seconds of audio fade at every join: a hard cut mid-waveform clicks


def render(video, start: float, end: float, out: Path, words: list[dict], burn: bool = True,
           orientation: str = "9:16", fps: int | None = None, ranges: list[tuple[float, float]] | None = None,
           emphasis: list[str] = (), layers: list[dict] = ()) -> None:
    """Write out (mp4), its .ass captions and a .jpg cover. `ranges`: the source spans to keep, in play order
    (tighten.plan); default the whole [start, end]. `burn`: draw the captions into the video (off when the source
    already has its own); the .ass file is written either way. `fps`: force 30/60 output (else the source's own)."""
    (rw, rh), (width, height) = ORIENTATIONS[orientation]
    ranges = ranges or [(start, end)]
    out = out.resolve()
    timed = retime(words, ranges)
    total = sum(b - a for a, b in ranges)
    out.with_suffix(".ass").write_text(captions(timed, 0, total, width, height, emphasis), encoding="utf-8")

    # one input seek to the earliest kept second, then every range is trimmed relative to it
    s0, s1 = min(a for a, _ in ranges), max(b for _, b in ranges)
    graph, joins = [], ""
    for i, (a, b) in enumerate(ranges):
        d = b - a
        graph.append(f"[0:v]trim=start={a - s0:.3f}:end={b - s0:.3f},setpts=PTS-STARTPTS,"
                     f"{crop_filter(video, a, b, (rw, rh))},scale={width}:{height},setsar=1[v{i}]")
        graph.append(f"[0:a]atrim=start={a - s0:.3f}:end={b - s0:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={FADE},afade=t=out:st={max(0, d - FADE):.3f}:d={FADE}[a{i}]")
        joins += f"[v{i}][a{i}]"
    # cwd = output dir and relative paths, so filter args carry no Windows drive colons (they break filter parsing)
    fonts = Path(os.path.relpath(FONTS, out.parent)).as_posix()
    burned = f",ass={out.stem}.ass:fontsdir={fonts}" if burn else ""
    graph.append(f"{joins}concat=n={len(ranges)}:v=1:a=1[cv][ca]")
    graph.append(f"[cv]null{burned}[vb]")
    motion_args, motion_chain, top = motion.overlay_graph("vb", list(layers), 1)  # animated hook/callouts on top
    graph += motion_chain
    graph.append(f"[{top}]format=yuv420p[vout]")
    graph.append("[ca]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    script = out.with_suffix(".graph")
    script.write_text(";\n".join(graph), encoding="utf-8")  # many ranges overflow Windows' 32K command line
    try:
        ffmpeg("-ss", f"{s0:.3f}", "-t", f"{s1 - s0:.3f}", "-i", str(Path(video).resolve()), *motion_args,
               "-/filter_complex", script.name, "-map", "[vout]", "-map", "[aout]", "-ar", "48000",
               *(("-r", str(fps)) if fps else ()),
               # a high-quality master: every platform re-encodes on upload, so artifacts compound
               "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.name, cwd=out.parent)
    finally:
        script.unlink(missing_ok=True)
    # cover = frame at 1 s: the speaker already framed
    ffmpeg("-ss", "1", "-i", out.name, "-frames:v", "1", "-q:v", "3", out.with_suffix(".jpg").name, cwd=out.parent)
