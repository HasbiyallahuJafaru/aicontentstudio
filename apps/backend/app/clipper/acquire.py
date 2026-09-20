"""Source acquisition: a local file path passes straight through; an http(s) URL downloads with yt-dlp."""
import hashlib
import os
from pathlib import Path

import yt_dlp

from app.errors import UserError


def acquire(source: str, root: Path, progress=lambda percent: None, meta: dict | None = None) -> tuple[Path, Path]:
    """Return (video, work dir). The work dir under `root` is named by the file hash / video id: that name is the
    transcript cache key. `progress(percent)` fires in >=5% steps while a link downloads. `meta` (a dict the
    caller owns) receives the source's own title when the extractor reports one."""
    if Path(source).is_file():
        with open(source, "rb") as f:
            work = root / hashlib.file_digest(f, "sha256").hexdigest()[:16]
        work.mkdir(parents=True, exist_ok=True)
        return Path(source), work
    if not source.startswith(("http://", "https://")):
        raise UserError("Enter a video URL or a file path that exists on this computer.", source)
    opts = {
        "format": "bv*+ba/b",
        # prefer H.264/AAC: YouTube's default pick is often AV1, which is several times slower to decode on CPU
        "format_sort": ["res:1080", "vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
        "outtmpl": str(root / "%(extractor_key)s-%(id)s" / "source.%(ext)s"),
        "noplaylist": True,
        "js_runtimes": {"deno": {}, "node": {}},  # YouTube extraction needs a JS runtime now
        "retries": 10,  # the library defaults to no retries (only its CLI sets 10)
        "fragment_retries": 10,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "progress_hooks": [lambda d: reported(d.get("downloaded_bytes"),
                                              d.get("total_bytes") or d.get("total_bytes_estimate"))],
    }
    if os.environ.get("YTDLP_PROXY"):  # ponytail: escape hatch for blocked networks; delete if never used
        opts["proxy"] = os.environ["YTDLP_PROXY"]
    last = -5

    def reported(done, total):  # percent of the current file; video and audio streams each count 0-100
        nonlocal last
        if done and total and (percent := min(100, int(done * 100 / total))) >= last + 5:
            last = percent
            progress(percent)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source)
            video = Path(info["requested_downloads"][0]["filepath"])
            if meta is not None and info.get("title"):
                meta["title"] = info["title"]
    except yt_dlp.utils.DownloadError as e:
        if "not a bot" in str(e) or "Sign in to confirm" in str(e):
            raise UserError("The video host refused this download (bot check). Upload the video file instead, "
                            "or try again later.", str(e)[:300]) from e
        raise
    return video, video.parent
