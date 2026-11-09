"""FFmpeg/ffprobe discipline for the clip engine: argv arrays, -nostdin + DEVNULL stdin (ffmpeg polls an
inherited Electron stdin pipe and can hang forever after finishing its encode), stderr to a temp file
(a stderr pipe deadlocks or makes ffmpeg exit 1 mid-teardown), a hard timeout as the backstop."""
import re
import subprocess
import tempfile
import threading

from app import config
from app.errors import UserError


STALL_SECS = 180  # no progress from ffmpeg for this long = wedged; same budget as render.py


def ffmpeg(*args, cwd=None, timeout: int = 3600, loglevel: str = "error") -> str:
    """Run ffmpeg; returns its log (stderr) for filters that report through it, like silencedetect. A watchdog
    kills it when its -progress output goes quiet for STALL_SECS, so a wedged encode never holds a clip job for
    the whole hour-long timeout."""
    stalled = threading.Event()
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen([config.FFMPEG, "-hide_banner", "-loglevel", loglevel, "-y", "-nostdin",
                                 "-nostats", "-progress", "pipe:1", *args],
                                cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errf,
                                text=True, encoding="utf-8", errors="replace")
        kill = lambda: (stalled.set(), proc.kill())  # noqa: E731
        deadline = threading.Timer(timeout, kill)
        deadline.start()
        watchdog = threading.Timer(STALL_SECS, kill)
        watchdog.start()
        try:
            for _ in proc.stdout:  # every progress line proves ffmpeg is alive
                watchdog.cancel()
                watchdog = threading.Timer(STALL_SECS, kill)
                watchdog.start()
            proc.wait()
        finally:
            watchdog.cancel()
            deadline.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
        errf.seek(0)
        log = errf.read().decode("utf-8", "replace")
        if stalled.is_set():
            raise UserError("FFmpeg took too long on this video and was stopped.",
                            f"no progress for {STALL_SECS}s or over {timeout}s: {' '.join(map(str, args[:6]))}")
        if proc.returncode != 0:
            raise UserError("FFmpeg could not process this video.", log[-500:])
        return log


def frame_rate(media) -> float | None:
    """The video stream's frame rate (r_frame_rate), or None when there is no readable video."""
    proc = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=r_frame_rate", "-of", "csv=p=0", str(media)],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    try:
        num, _, den = proc.stdout.strip().partition("/")
        rate = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return rate if 1 <= rate <= 240 else None


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
