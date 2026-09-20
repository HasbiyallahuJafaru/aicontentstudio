"""FFmpeg/ffprobe discipline for the clip engine: argv arrays, -nostdin + DEVNULL stdin (ffmpeg polls an
inherited Electron stdin pipe and can hang forever after finishing its encode), stderr to a temp file
(a stderr pipe deadlocks or makes ffmpeg exit 1 mid-teardown), a hard timeout as the backstop."""
import subprocess
import tempfile

from app import config
from app.errors import UserError


def ffmpeg(*args, cwd=None, timeout: int = 3600) -> None:
    with tempfile.TemporaryFile() as errf:
        try:
            proc = subprocess.run([config.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-nostdin", *args],
                                  cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errf,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            raise UserError("FFmpeg took too long on this video and was stopped.",
                            f"timed out after {timeout}s: {' '.join(args[:6])}")
        if proc.returncode != 0:
            errf.seek(0)
            raise UserError("FFmpeg could not process this video.", errf.read().decode("utf-8", "replace")[-500:])


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
