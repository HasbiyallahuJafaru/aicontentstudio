"""Visual providers (PRD §15): one interface, Pexels and Unsplash behind it. Rendering never sees provider details."""
import asyncio
import logging
import os
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
    provider: Literal["pexels", "unsplash"]
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

    async def search_images(self, query: str, limit: int) -> list[Candidate]: ...
    async def search_videos(self, query: str, limit: int) -> list[Candidate]: ...
    async def download(self, asset: Candidate) -> bytes: ...
    async def download_thumb(self, asset: Candidate) -> bytes: ...


class _Http:
    """Shared plumbing: Windows cert store (see DeepSeekModel), bounded retries, human errors (PRD §79)."""
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

    async def search_images(self, query, limit):
        d = await self.h.get_json(f"{self.URL}/v1/search", {"query": query, "per_page": limit, "orientation": "portrait"})
        return [Candidate(provider=self.name, provider_asset_id=str(p["id"]), asset_type="image",
                          creator=p.get("photographer", ""), source_url=p.get("url", ""),
                          download_url=p["src"]["large2x"], thumb_url=p["src"]["medium"],
                          width=p.get("width", 0), height=p.get("height", 0))
                for p in d.get("photos", [])]

    async def search_videos(self, query, limit):
        d = await self.h.get_json(f"{self.URL}/videos/search", {"query": query, "per_page": limit, "orientation": "portrait"})
        out = []
        for v in d.get("videos", []):
            file = _best_video_file(v.get("video_files", []))
            if file:
                out.append(Candidate(provider=self.name, provider_asset_id=str(v["id"]), asset_type="video",
                                     creator=v.get("user", {}).get("name", ""), source_url=v.get("url", ""),
                                     download_url=file["link"], thumb_url=v.get("image", ""),
                                     width=v.get("width", 0), height=v.get("height", 0),
                                     fps=float(file.get("fps") or 0), duration=float(v.get("duration") or 0)))
        return out

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

    async def search_images(self, query, limit):
        d = await self.h.get_json(f"{self.URL}/search/photos", {"query": query, "per_page": limit, "orientation": "portrait"})
        return [Candidate(provider=self.name, provider_asset_id=str(p["id"]), asset_type="image",
                          creator=p.get("user", {}).get("name", ""), source_url=p.get("links", {}).get("html", ""),
                          download_url=p["links"]["download_location"], thumb_url=p["urls"]["small"],
                          width=p.get("width", 0), height=p.get("height", 0))
                for p in d.get("results", [])]

    async def search_videos(self, query, limit):
        return []

    async def download(self, asset):
        # download_location with the auth header counts the attribution ping Unsplash asks for; it redirects to bytes.
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
