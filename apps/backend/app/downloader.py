"""Plain video downloader (ported from ClipperAi's downloader tool, minus its web abuse guards: here it runs for one
person on their own machine). Paste a link, the MP4 lands in the Downloads folder; the UI polls `status`."""
import subprocess
import threading
import uuid
from pathlib import Path

import yt_dlp

from app import settings
from app.clipper.acquire import friendly, options
from app.errors import UserError, explain

# ponytail: the default Downloads folder; a user who moved theirs (Known Folder redirect) still gets ~/Downloads
FOLDER = Path.home() / "Downloads"
_lock = threading.Lock()
_jobs: dict[str, dict] = {}  # token -> {status: fetching|ready|error, progress 0-100, title, path, error}


def start(url: str) -> dict:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise UserError("Paste a video link (https://...) to download it.", url)
    token = uuid.uuid4().hex
    with _lock:
        _jobs[token] = {"status": "fetching", "progress": 0, "title": None, "path": None, "error": None}
    threading.Thread(target=_work, args=(token, url), daemon=True, name=f"download-{token[:6]}").start()
    return {"token": token}


def _work(token: str, url: str) -> None:
    cookies = settings.get()["ytdlp_cookies"]

    def reported(done, total):  # video and audio each run 0-100; the merge finishes the last few percent
        if done and total:
            _set(token, progress=max(_jobs[token]["progress"], min(95, int(done * 95 / total))))

    FOLDER.mkdir(parents=True, exist_ok=True)
    # title first, id after it: two videos with the same title never overwrite each other
    opts = options(str(FOLDER / "%(title).120B [%(id)s].%(ext)s"), cookies, reported) | {"windowsfilenames": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url)
        path = Path(info["requested_downloads"][0]["filepath"])
        _set(token, status="ready", progress=100, title=info.get("title") or path.stem, path=str(path))
    except yt_dlp.utils.DownloadError as e:
        err = friendly(e, cookies)
        _set(token, status="error", error={"message": str(err), "detail": err.detail})
    except Exception as e:  # a thread has no caller to raise to: every failure lands in the status
        message, detail = explain(e)
        _set(token, status="error", error={"message": message, "detail": detail})


def _set(token: str, **fields) -> None:
    with _lock:
        _jobs[token] |= fields


def status(token: str) -> dict:
    with _lock:
        job = _jobs.get(token)
    if job is None:
        raise UserError("That download is no longer tracked. Start it again.", token)
    return dict(job)


def reveal(token: str) -> dict:
    """Open Explorer with the downloaded file selected. Only paths this module wrote can be opened."""
    path = status(token)["path"]
    if not path or not Path(path).is_file():
        raise UserError("The downloaded file isn't there any more.", str(path))
    subprocess.Popen(["explorer", f"/select,{path}"])  # ponytail: Windows only, like the app
    return {"ok": True}
