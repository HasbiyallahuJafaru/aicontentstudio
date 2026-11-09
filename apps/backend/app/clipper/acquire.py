"""Source acquisition: a local file path passes straight through; an http(s) URL downloads with yt-dlp."""
import hashlib
import os
from pathlib import Path

import yt_dlp

from app.errors import UserError


def acquire(source: str, root: Path, progress=lambda percent: None, meta: dict | None = None,
            cookies: str = "") -> tuple[Path, Path]:
    """Return (video, work dir). The work dir under `root` is named by the file hash / video id: that name is the
    transcript cache key. `progress(percent)` fires in >=5% steps while a link downloads. `meta` (a dict the
    caller owns) receives the source's own title when the extractor reports one. `cookies`: a browser name
    (firefox, chrome, edge, ...) or a cookies.txt path, for hosts that bot-check anonymous downloads."""
    if Path(source).is_file():
        st = Path(source).stat()  # hashing a multi-GB file on every run took longer than the cache saved
        work = root / hashlib.sha256(f"{Path(source).resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
        work.mkdir(parents=True, exist_ok=True)
        return Path(source), work
    if not source.startswith(("http://", "https://")):
        raise UserError("Enter a video URL or a file path that exists on this computer.", source)
    last = -5

    def reported(done, total):  # percent of the current file; video and audio streams each count 0-100
        nonlocal last
        if done and total and (percent := min(100, int(done * 100 / total))) >= last + 5:
            last = percent
            progress(percent)

    opts = options(str(root / "%(extractor_key)s-%(id)s" / "source.%(ext)s"), cookies, reported)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source)
            video = Path(info["requested_downloads"][0]["filepath"])
            if meta is not None and info.get("title"):
                meta["title"] = info["title"]
    except yt_dlp.utils.DownloadError as e:
        raise friendly(e, cookies) from e
    return video, video.parent


def options(outtmpl: str, cookies: str = "", reported=lambda done, total: None) -> dict:
    """yt-dlp settings shared by clipping and the plain downloader. `reported(done_bytes, total_bytes)` follows the
    download."""
    opts = {
        "format": "bv*+ba/b",
        # prefer H.264/AAC: YouTube's default pick is often AV1, which is several times slower to decode on CPU
        "format_sort": ["res:1440", "vcodec:h264", "acodec:aac"],  # 1440p: a 9:16 crop of 1080p is ~2x upscaled
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "max_filesize": 8 * 1024 ** 3,  # 8 GB: a 2-hour 1440p talk fits; a mistaken 4K livestream doesn't
        "js_runtimes": {"deno": {}, "node": {}},  # YouTube extraction needs a JS runtime now
        "retries": 10,  # the library defaults to no retries (only its CLI sets 10)
        "fragment_retries": 10,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "progress_hooks": [lambda d: reported(d.get("downloaded_bytes"),
                                              d.get("total_bytes") or d.get("total_bytes_estimate"))],
    }
    if cookies and Path(cookies).is_file():
        opts["cookiefile"] = cookies
    elif cookies:
        opts["cookiesfrombrowser"] = (cookies.lower(),)
    if os.environ.get("YTDLP_PROXY"):  # ponytail: escape hatch for blocked networks; delete if never used
        opts["proxy"] = os.environ["YTDLP_PROXY"]
    return opts


# (phrases yt-dlp or the site puts in the error, what to tell the person); first match wins, so the specific
# cases sit above the general ones
_REASONS = [
    (("http error 429", "too many requests", "rate-limit", "rate limit", "ratelimit"),
     "The video site is limiting downloads from your internet connection right now (too many requests). Wait "
     "15 to 30 minutes and try again, or download the video in your browser and choose the file instead."),
    (("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"),
     "This video is age-restricted. Set YouTube cookies in Settings to a browser where you're signed in, or "
     "choose the video file instead."),
    (("not a bot", "sign in to confirm"),
     "The video site wants to check you're not a bot. Set YouTube cookies in Settings to a browser you're "
     "signed in with (Firefox works best), or choose the video file instead."),
    (("http error 403", "forbidden", "your ip"),
     "The video site blocked this download from your internet connection. This often happens on VPNs, work or "
     "shared networks. Try again later or on another network, or choose the video file instead."),
    (("private video",),
     "This video is private, so it can't be downloaded. Ask the owner for the file, or choose a different video."),
    (("members-only", "members only", "join this channel"),
     "This video is for channel members only, so it can't be downloaded."),
    (("not available in your country", "geo restrict", "geo-restrict", "not made this video available in your"),
     "This video isn't available in your country."),
    (("is live", "live event will begin", "premieres in", "this live stream"),
     "This is a live stream or a premiere that hasn't ended. Try again once it has finished."),
    (("video unavailable", "has been removed", "no longer available", "does not exist", "http error 404",
      "account associated with this video has been terminated"),
     "This video isn't available. It may have been removed, or the link is wrong."),
    (("unsupported url",),
     "That link isn't a video page this app can download from. Paste the link of the video itself."),
    (("requested format is not available", "no video formats found"),
     "The video site didn't offer a downloadable copy of this video. Try another link, or choose the video "
     "file instead."),
    (("getaddrinfo failed", "name or service not known", "network is unreachable", "timed out",
      "connection reset", "connection refused", "unable to download webpage", "urlopen error",
      "remote end closed connection", "no address associated"),
     "Couldn't reach the video site. Check your internet connection and try again."),
]


def friendly(e: Exception, cookies: str = "") -> UserError:
    """A download failure in words a person can act on. Unrecognised failures get a calm general line; the raw
    error always stays in the technical details."""
    text = str(e).lower()
    if cookies and ("cookie" in text or "decrypt" in text):
        return UserError("Couldn't read cookies from that browser. Close it and try again, use Firefox, or "
                         "export a cookies.txt file and give its path in Settings.", str(e)[:500])
    for phrases, message in _REASONS:
        if any(p in text for p in phrases):
            if cookies and phrases[0] in ("confirm your age", "not a bot"):
                message = ("The video site still refused with your cookies. Sign in to the site in that browser, "
                           "close the browser, and try again, or choose the video file instead.")
            return UserError(message, str(e)[:500])
    return UserError("Couldn't download that video. Check the link and try again, or download it in your browser "
                     "and choose the file instead.", str(e)[:500])
