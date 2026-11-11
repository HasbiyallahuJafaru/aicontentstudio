"""Clip render: the kept source ranges joined into one clip, each face-tracked, captions retimed and burned, and a
cover frame, all through our ffmpeg discipline."""
import os
from pathlib import Path

from app import motion
from app.render import DELIVERY, audio_misstamped
from app.errors import UserError
from app.clipper.captions import FONTS, captions
from app.clipper.crop import crop_filter
from app.clipper.ff import ffmpeg, frame_rate
from app.clipper.tighten import retime

# orientations a clip can take: crop ratio (w, h) and output pixel size
ORIENTATIONS = {"9:16": ((9, 16), (1080, 1920)), "16:9": ((16, 9), (1920, 1080)), "1:1": ((1, 1), (1080, 1080))}
FADE = 0.01  # seconds of audio fade at every join: a hard cut mid-waveform clicks


def render(video, start: float, end: float, out: Path, words: list[dict], burn: bool = True,
           orientation: str = "9:16", fps: int | None = None, ranges: list[tuple[float, float]] | None = None,
           emphasis: list[str] = (), layers: list[dict] = (), zooms: list[float] | None = None,
           caption_style: dict | None = None, music: Path | None = None) -> None:
    """Write out (mp4), its .ass captions and a .jpg cover. `ranges`: the source spans to keep, in play order
    (tighten.plan); default the whole [start, end]. `zooms`: each range's push-in (1.0 = the tracked crop as is).
    `burn`: draw the captions into the video (off when the source already has its own); the .ass file is written
    either way. `fps`: force 30/60 output (else the source's own). `music`: a bed blended under the speech
    (owner 2026-11-10: every clip gets our music, mixed so it sounds like part of the original edit)."""
    (rw, rh), (width, height) = ORIENTATIONS[orientation]
    ranges = ranges or [(start, end)]
    zooms = zooms or [1.0] * len(ranges)
    out = out.resolve()
    # ranges land on the source's frame grid: trim rounds each piece to whole frames while the captions were
    # retimed on the exact sums, so the words drifted ~0.2 s behind the voice over 28 joins (2026-11-09)
    rate = frame_rate(video)
    if rate:
        ranges = [(round(a * rate) / rate, round(b * rate) / rate) for a, b in ranges]
        ranges = [(a, b) for a, b in ranges if b > a] or [(round(start * rate) / rate, round(end * rate) / rate)]
    timed = retime(words, ranges)
    total = sum(b - a for a, b in ranges)
    out.with_suffix(".ass").write_text(captions(timed, 0, total, width, height, emphasis, caption_style), encoding="utf-8")

    # every range is its own seeked input: trimming one shared decode made concat buffer every frame between a
    # late cold-open teaser and the body (4.2 GB at 1080p, 2026-11-09); separate inputs decode only what plays
    graph, joins, inputs = [], "", []
    for i, ((a, b), z) in enumerate(zip(ranges, zooms)):
        d = b - a
        inputs += ["-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", str(Path(video).resolve())]
        # push-in centred across, a little above centre down: the face sits in the upper half, keep its headroom
        push = f",crop=iw/{z:.3f}:ih/{z:.3f}:(iw-iw/{z:.3f})/2:(ih-ih/{z:.3f})*0.4" if z > 1.001 else ""
        graph.append(f"[{i}:v]setpts=PTS-STARTPTS,"
                     f"{crop_filter(video, a, b, (rw, rh))}{push},scale={width}:{height},setsar=1[v{i}]")
        graph.append(f"[{i}:a]asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={FADE},afade=t=out:st={max(0, d - FADE):.3f}:d={FADE}[a{i}]")
        joins += f"[v{i}][a{i}]"
    # cwd = output dir and relative paths, so filter args carry no Windows drive colons (they break filter parsing)
    fonts = Path(os.path.relpath(FONTS, out.parent)).as_posix()
    burned = f",ass={out.stem}.ass:fontsdir={fonts}" if burn else ""
    graph.append(f"{joins}concat=n={len(ranges)}:v=1:a=1[cv][ca]")
    graph.append(f"[cv]null{burned}[vb]")
    motion_args, motion_chain, top = motion.overlay_graph("vb", list(layers), len(ranges))  # animated hook/callouts on top
    graph += motion_chain
    graph.append(f"[{top}]scale=out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[vout]")
    # loudnorm stamps its first ~3 s lookahead wrong (frames 1 sample apart, then a 2.4 s jump): desktop players
    # ignore it, but platform transcoders obey the stamps and speed up / drag the opening. Restamp from samples.
    if music is None:
        graph.append("[ca]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,asetpts=N/SR/TB[aout]")
    else:
        from app.music import CLIP_VOLUME
        m = len(ranges) + len(list(layers))  # the music input comes after the ranges and the motion layers
        inputs_tail = ["-stream_loop", "-1", "-i", str(Path(music).resolve())]
        # speech normalised first, then the bed: quiet, faded, and ducked gently (slow release) under every word so
        # it breathes with the speaker instead of pumping; the limiter keeps the sum under the platforms' ceiling
        graph.append("[ca]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,asplit=2[sp][key]")
        graph.append(f"[{m}:a]aresample=48000,volume={CLIP_VOLUME},afade=t=in:d=1.5,"
                     f"afade=t=out:st={max(total - 2, 0):.3f}:d=2,atrim=0:{total:.3f}[bed]")
        graph.append("[bed][key]sidechaincompress=threshold=0.02:ratio=4:attack=60:release=700[duck]")
        graph.append("[sp][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89,"
                     "asetpts=N/SR/TB[aout]")
    script = out.with_suffix(".graph")
    script.write_text(";\n".join(graph), encoding="utf-8")  # many ranges overflow Windows' 32K command line
    try:
        ffmpeg(*inputs, *motion_args, *(inputs_tail if music is not None else ()),
               "-/filter_complex", script.name, "-map", "[vout]", "-map", "[aout]", "-ar", "48000",
               *(("-r", str(fps)) if fps else ()),
               # a high-quality master: every platform re-encodes on upload, so artifacts compound
               "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-c:a", "aac", "-b:a", "192k", *DELIVERY, "-movflags", "+faststart", out.name, cwd=out.parent)
    finally:
        script.unlink(missing_ok=True)
    if audio_misstamped(out):
        raise UserError("The clip's audio came out with uneven timestamps.", f"{out.name}: AAC packets misstamped")
    # cover = frame at 1.6 s: the speaker framed and the hook title settled (at 1 s it was mid-animation)
    ffmpeg("-ss", f"{min(1.6, total / 2):.2f}", "-i", out.name, "-frames:v", "1", "-q:v", "3", out.with_suffix(".jpg").name, cwd=out.parent)
