"""FFmpeg/ffprobe discipline for the clip engine: argv arrays, -nostdin + DEVNULL stdin (ffmpeg polls an
inherited Electron stdin pipe and can hang forever after finishing its encode), stderr to a temp file
(a stderr pipe deadlocks or makes ffmpeg exit 1 mid-teardown), a hard timeout as the backstop."""
import re
import subprocess
import tempfile

from app import config
from app.errors import UserError


def ffmpeg(*args, cwd=None, timeout: int = 3600, loglevel: str = "error") -> str:
    """Run ffmpeg; returns its log (stderr) for filters that report through it, like silencedetect."""
    with tempfile.TemporaryFile() as errf:
        try:
            proc = subprocess.run([config.FFMPEG, "-hide_banner", "-loglevel", loglevel, "-y", "-nostdin", *args],
                                  cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errf,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            raise UserError("FFmpeg took too long on this video and was stopped.",
                            f"timed out after {timeout}s: {' '.join(args[:6])}")
        errf.seek(0)
        log = errf.read().decode("utf-8", "replace")
        if proc.returncode != 0:
            raise UserError("FFmpeg could not process this video.", log[-500:])
        return log


def silences(media, start: float, end: float, noise_db: int = -43, min_len: float = 0.25) \
        -> list[tuple[float, float]] | None:
    """Silent stretches of the audio in [start, end], in source seconds. None when there is no usable answer
    (no audio, a failed probe, or a source that never drops below the floor, like speech over a music bed): the
    caller then trusts the word timings alone."""
    try:
        log = ffmpeg("-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(media), "-vn",
                     "-af", f"silencedetect=n={noise_db}dB:d={min_len}", "-f", "null", "-",
                     timeout=300, loglevel="info")
    except UserError:
        return None
    out, open_at = [], None
    for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", log):
        t = start + max(0.0, float(m.group(2)))
        if m.group(1) == "start":
            open_at = t
        elif open_at is not None:
            out.append((open_at, t))
            open_at = None
    if open_at is not None:  # silent through the end of the span
        out.append((open_at, end))
    return out or None


def duration_of(media) -> float:
    proc = subprocess.run([config.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                           str(media)],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    if proc.returncode != 0:
        raise UserError("This video file could not be read.", proc.stderr[-300:])
    try:
        return float(proc.stdout)
    except ValueError:
        raise UserError("This video has no readable duration.", proc.stdout[:200])
