"""A link's own name and picture a moment after it is pasted, before the slow download (ported from ClipperAi's
fetch_title_async): public, keyless oEmbed endpoints. Cosmetic, so any failure leaves the project as it was and the
clip job still renames it from the downloaded video."""
import json
import logging
import ssl
import threading
from urllib.parse import urlparse

import httpx

from app import config
from app.database import connect

log = logging.getLogger("clipper.preview")
# Measured by ClipperAi 2026-09-18: these answer with a title. Reddit, Instagram and Facebook do not (403 / need an
# app token); those keep their URL name until the download reports the real title.
OEMBED = {"youtube.com": "https://www.youtube.com/oembed", "youtu.be": "https://www.youtube.com/oembed",
          "dailymotion.com": "https://www.dailymotion.com/services/oembed",
          "dai.ly": "https://www.dailymotion.com/services/oembed",
          "tiktok.com": "https://www.tiktok.com/oembed", "soundcloud.com": "https://soundcloud.com/oembed",
          "x.com": "https://publish.twitter.com/oembed", "twitter.com": "https://publish.twitter.com/oembed",
          "pinterest.com": "https://www.pinterest.com/oembed.json", "vimeo.com": "https://vimeo.com/api/oembed.json"}
THUMBS = "clipwork/thumbs"  # under media/, one picture per project
MAX_THUMB = 5 * 1024 * 1024


def endpoint(url: str) -> str | None:
    """The oEmbed service for this link's host (or a subdomain of it), else None."""
    host = (urlparse(url).hostname or "").lower()
    return next((service for site, service in OEMBED.items() if host == site or host.endswith("." + site)), None)


def start(project_id: str, url: str, placeholder: str) -> None:
    if endpoint(url):
        threading.Thread(target=fetch, args=(project_id, url, placeholder), daemon=True).start()


def fetch(project_id: str, url: str, placeholder: str) -> None:
    """Name the project after the video (unless something renamed it already) and store its thumbnail."""
    try:
        thumb = None
        # Windows cert store (works behind TLS-inspecting local CAs); a browser agent, some hosts refuse the default
        with httpx.Client(verify=ssl.create_default_context(), timeout=10, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"}) as http:
            info = http.get(endpoint(url), params={"url": url, "format": "json"}).raise_for_status().json()
            src = info.get("thumbnail_url") or ""
            if src.startswith("https://"):
                r = http.get(src)
                if r.is_success and r.headers.get("content-type", "").startswith("image/") and len(r.content) <= MAX_THUMB:
                    path = config.MEDIA_DIR / THUMBS / f"{project_id}.jpg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(r.content)
                    thumb = f"{THUMBS}/{project_id}.jpg"
        title = str(info.get("title") or info.get("author_name") or "").strip()  # X gives the account, not the post
        with connect() as conn:
            row = conn.execute("SELECT name, brief FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:  # deleted while we fetched
                return
            brief = json.loads(row["brief"]) | ({"thumb": thumb} if thumb else {})
            name = title[:80] if title and row["name"] == placeholder else row["name"]
            conn.execute("UPDATE projects SET name = ?, brief = ? WHERE id = ?",
                         (name, json.dumps(brief, ensure_ascii=False), project_id))
    except Exception as e:
        log.info("link preview for %s failed: %r", url, e)
