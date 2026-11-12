"""Visual providers (PRD §15): one interface, Pexels and Unsplash behind it. Rendering never sees provider details."""
import asyncio
import logging
import os
import re
import ssl
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.errors import UserError

log = logging.getLogger("assets")

MAX_BYTES = 300 * 1024 * 1024  # refuse absurd downloads before they fill the disk


class Candidate(BaseModel):
    """One search result, metadata only. `download_url` is fetched for the chosen asset, `thumb_url` for scoring."""
    provider: Literal["pexels", "unsplash", "commons"]
    provider_asset_id: str = Field(min_length=1)
    asset_type: Literal["image", "video"]
    creator: str = ""
    source_url: str = ""
    download_url: str
    thumb_url: str
    width: int = 0
    height: int = 0
    fps: float = 0
    duration: float = 0


class VisualProvider:
    """PRD §15 interface. Implementations raise UserError with human messages; nothing here is provider-specific upward."""

    name: str = ""
    LICENSE = ""

    async def search_images(self, query: str, limit: int, color: str | None = None) -> list[Candidate]: ...
    async def search_videos(self, query: str, limit: int) -> list[Candidate]: ...
    async def download(self, asset: Candidate) -> bytes: ...
    async def download_thumb(self, asset: Candidate) -> bytes: ...

    async def by_id(self, slug: str, kind: str) -> Candidate:
        """One asset from its page link's last path part (assets.add_link)."""
        raise UserError(f"{self.name.title()} links aren't supported.")


class _Http:
    """Shared plumbing: Windows cert store (see OpenRouterModel), bounded retries, human errors (PRD §79)."""
    RETRIES = 2

    def __init__(self, label: str, headers: dict, transport: httpx.AsyncBaseTransport | None = None):
        self.label = label
        self.http = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(60, connect=15),
                                      verify=ssl.create_default_context(), transport=transport,
                                      follow_redirects=True)

    async def get_json(self, url: str, params: dict) -> dict:
        for attempt in range(self.RETRIES + 1):
            try:
                r = await self.http.get(url, params=params)
            except httpx.HTTPError as e:
                if attempt == self.RETRIES:
                    raise UserError(f"Couldn't reach {self.label}. Check your internet connection.", repr(e))
            else:
                if r.status_code in (401, 403):
                    raise UserError(f"{self.label} authentication failed. Check the API key in Settings.", r.text[:500])
                if r.status_code == 404:  # a pasted link to something removed or mistyped: retrying won't help
                    raise UserError(f"{self.label} couldn't find that photo or video. Check the link.", r.text[:300])
                if r.status_code == 429:
                    raise UserError(f"{self.label} is rate limiting us. Try again in a few minutes.", r.text[:500])
                if r.is_success:
                    return r.json()
                if attempt == self.RETRIES:
                    raise UserError(f"{self.label} is having trouble right now. Try again in a few minutes.",
                                    f"HTTP {r.status_code}: {r.text[:500]}")
            if attempt < self.RETRIES:
                await asyncio.sleep(2 ** attempt)
        raise UserError(f"{self.label} returned no usable response.", "")

    async def fetch(self, url: str) -> bytes:
        try:
            r = await self.http.get(url)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise UserError(f"Couldn't download a {self.label} asset.", repr(e))
        if len(r.content) > MAX_BYTES:
            raise UserError(f"That {self.label} asset is too large to download.",
                            f"{len(r.content)} bytes exceeds the {MAX_BYTES} byte cap")
        return r.content


class PexelsProvider(VisualProvider):
    name = "pexels"
    URL = os.environ.get("ACS_PEXELS_URL", "https://api.pexels.com").rstrip("/")  # env: tests/proxies
    LICENSE = "Pexels License"

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None):
        self.h = _Http("Pexels", {"Authorization": api_key}, transport)

    async def search_images(self, query, limit, color=None):
        params = {"query": query, "per_page": limit, "orientation": "portrait"}
        if color:
            params["color"] = color  # Pexels filters photos by colour at the source (videos have no such filter)
        d = await self.h.get_json(f"{self.URL}/v1/search", params)
        return [self._photo(p) for p in d.get("photos", [])]

    def _photo(self, p: dict) -> Candidate:
        return Candidate(provider=self.name, provider_asset_id=str(p["id"]), asset_type="image",
                         creator=p.get("photographer", ""), source_url=p.get("url", ""),
                         download_url=p["src"]["large2x"], thumb_url=p["src"]["medium"],
                         width=p.get("width", 0), height=p.get("height", 0))

    def _video(self, v: dict) -> Candidate | None:
        file = _best_video_file(v.get("video_files", []))
        if not file:
            return None
        return Candidate(provider=self.name, provider_asset_id=str(v["id"]), asset_type="video",
                         creator=v.get("user", {}).get("name", ""), source_url=v.get("url", ""),
                         download_url=file["link"], thumb_url=v.get("image", ""),
                         width=v.get("width", 0), height=v.get("height", 0),
                         fps=float(file.get("fps") or 0), duration=float(v.get("duration") or 0))

    async def by_id(self, slug, kind):
        m = re.search(r"(\d+)$", slug)  # pexels.com/photo/calm-sea-at-dusk-1234567/
        if not m:
            raise UserError("That Pexels link has no photo or video number in it.", slug)
        if kind == "video":
            c = self._video(await self.h.get_json(f"{self.URL}/videos/videos/{m[1]}", {}))
            if c is None:
                raise UserError("That Pexels video has no portrait or square file the studio can use.", slug)
            return c
        return self._photo(await self.h.get_json(f"{self.URL}/v1/photos/{m[1]}", {}))

    async def search_videos(self, query, limit):
        d = await self.h.get_json(f"{self.URL}/videos/search", {"query": query, "per_page": limit, "orientation": "portrait"})
        return [c for v in d.get("videos", []) if (c := self._video(v))]

    async def download(self, asset):
        return await self.h.fetch(asset.download_url)

    async def download_thumb(self, asset):
        return await self.h.fetch(asset.thumb_url)


def _best_video_file(files: list[dict]) -> dict | None:
    """Portrait-usable mp4 closest to 1080x1920 without going over; anything taller only if nothing fits."""
    mp4s = [f for f in files if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= (f.get("width") or 0)]
    if not mp4s:
        return None
    fits = [f for f in mp4s if (f.get("height") or 0) <= 1920]
    key = lambda f: abs(1920 - (f.get("height") or 0))  # noqa: E731
    return min(fits or mp4s, key=key)


class UnsplashProvider(VisualProvider):
    """Photos only: Unsplash has no video API, so search_videos is honestly empty."""
    name = "unsplash"
    URL = os.environ.get("ACS_UNSPLASH_URL", "https://api.unsplash.com").rstrip("/")
    LICENSE = "Unsplash License"

    def __init__(self, access_key: str, transport: httpx.AsyncBaseTransport | None = None):
        self.h = _Http("Unsplash", {"Authorization": f"Client-ID {access_key}"}, transport)

    async def search_images(self, query, limit, color=None):
        params = {"query": query, "per_page": limit, "orientation": "portrait"}
        if color:
            params["color"] = color
        d = await self.h.get_json(f"{self.URL}/search/photos", params)
        return [self._photo(p) for p in d.get("results", [])]

    def _photo(self, p: dict) -> Candidate:
        return Candidate(provider=self.name, provider_asset_id=str(p["id"]), asset_type="image",
                         creator=p.get("user", {}).get("name", ""), source_url=p.get("links", {}).get("html", ""),
                         download_url=p["links"]["download_location"], thumb_url=p["urls"]["small"],
                         width=p.get("width", 0), height=p.get("height", 0))

    async def by_id(self, slug, kind):
        if kind == "video":
            raise UserError("Unsplash has photos only. Use a Pexels link for a video clip.")
        # unsplash.com/photos/a-man-on-a-cliff-XyZ12abCDeF: the id is the slug's last part (older links are the id)
        tried = list(dict.fromkeys([slug.rsplit("-", 1)[-1], slug[-11:], slug]))
        for i, pid in enumerate(tried):
            try:
                return self._photo(await self.h.get_json(f"{self.URL}/photos/{pid}", {}))
            except UserError:
                if i == len(tried) - 1:
                    raise

    async def search_videos(self, query, limit):
        return []

    async def download(self, asset):
        # download_location is Unsplash's required download ping: it counts the download and answers JSON
        # {"url": <the photo>}, never image bytes (checked against unsplash.com/documentation 2026-11-12; this used
        # to store that JSON as the photo). The photo URL is imgix: sized to 1440 wide here, its ixid kept.
        url = (await self.h.get_json(asset.download_url, {}))["url"]
        return await self.h.fetch(url + ("&" if "?" in url else "?") + "w=1440&fm=jpg&q=85")

    async def download_thumb(self, asset):
        return await self.h.fetch(asset.thumb_url)


class CommonsProvider(VisualProvider):
    """Archival stills for documentaries (owner 2026-11-10): real portraits, maps, manuscripts and artefacts from
    Wikimedia Commons. No key. Only Public domain and CC0 files are offered, so nothing needs a credit line.
    ponytail: licence read from Commons' LicenseShortName; CC BY / BY-SA files (most modern photos) are skipped
    rather than carrying attribution through to every post."""
    name = "commons"
    URL = os.environ.get("ACS_COMMONS_URL", "https://commons.wikimedia.org/w/api.php")
    LICENSE = "Public domain / CC0 (Wikimedia Commons)"
    FREE = ("public domain", "cc0", "pd", "no restrictions")

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        # Wikimedia refuses clients without a descriptive User-Agent
        self.h = _Http("Wikimedia Commons", {"User-Agent": "AiContentStudio/0.1 (https://ytclipper.xyz)"}, transport)

    async def search_images(self, query, limit, color=None):
        d = await self.h.get_json(self.URL, {
            "action": "query", "format": "json", "formatversion": 2, "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": limit * 2, "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": 1600,
            "iiextmetadatafilter": "LicenseShortName|Artist"})
        out = []
        for page in sorted(d.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0)):
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value", "").lower()
            if not any(lic.startswith(f) or f in lic for f in self.FREE) or not info.get("thumburl"):
                continue
            big = info["thumburl"]
            out.append(Candidate(provider=self.name, provider_asset_id=str(page["pageid"]), asset_type="image",
                                 creator=re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", ""))[:120],
                                 source_url=info.get("descriptionurl", ""), download_url=big,
                                 thumb_url=big.replace("/1600px-", "/400px-"),
                                 width=info.get("width", 0), height=info.get("height", 0)))
            if len(out) == limit:
                break
        return out

    async def search_videos(self, query, limit):
        return []

    async def download(self, asset):
        return await self.h.fetch(asset.download_url)

    async def download_thumb(self, asset):
        return await self.h.fetch(asset.thumb_url)


def get_providers() -> list[VisualProvider]:
    from app import config
    out: list[VisualProvider] = []
    if config.SECRETS.get("PEXELS_API_KEY"):
        out.append(PexelsProvider(config.SECRETS["PEXELS_API_KEY"]))
    if config.SECRETS.get("UNSPLASH_ACCESS_KEY"):
        out.append(UnsplashProvider(config.SECRETS["UNSPLASH_ACCESS_KEY"]))
    return out
