"""Milestone 3: provider parsing, selection scoring, dedup/cooldown and the visual phase. No network: fakes + MockTransport."""
import asyncio
import os
import struct
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

import httpx  # noqa: E402

from app import assets, config, content, database, jobs, projects, settings  # noqa: E402
from app.assets.providers import Candidate, PexelsProvider, UnsplashProvider, VisualProvider  # noqa: E402
from app.errors import UserError  # noqa: E402

from tests.test_content import BRIEF, FakeModel  # noqa: E402


def bmp(columns, size: int = 8) -> bytes:
    """A 24-bit BMP from one (r,g,b) tuple per pixel column (BMP stores BGR, so reverse on write)."""
    pixels = b"".join(bytes((c[2], c[1], c[0])) for _ in range(size) for c in columns)
    header = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
    header += struct.pack("<IiiHHIIiiII", 40, size, size, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    return header + pixels


STRIPES = [(200, 200, 200), (40, 40, 40)] * 4   # alternating columns
INVERTED = [(40, 40, 40), (200, 200, 200)] * 4  # opposite gradient
SOLID = [(128, 128, 128)] * 8
DARK = [(0, 0, 0), (12, 12, 12)] * 4            # near-black stripes: fails the quality floor


class FakeProvider(VisualProvider):
    name, LICENSE = "pexels", "Test License"

    def __init__(self, candidates: list[Candidate]):
        self.candidates = candidates
        self.downloads: list[str] = []
        self.thumb_downloads: list[str] = []

    async def search_images(self, query, limit):
        return [c for c in self.candidates if c.asset_type == "image"][:limit]

    async def search_videos(self, query, limit):
        return [c for c in self.candidates if c.asset_type == "video"][:limit]

    async def download(self, a):
        self.downloads.append(a.provider_asset_id)
        return b"asset-bytes-" + a.provider_asset_id.encode()

    async def download_thumb(self, a):
        self.thumb_downloads.append(a.provider_asset_id)
        return STRIPES_BYTES[a.provider_asset_id]


def thumb_for(pid: str) -> bytes:
    return SPECIAL.get(pid, bmp(STRIPES))


def make_thumbs(*pids: str, solid: tuple[str, ...] = (), dark: tuple[str, ...] = ()) -> None:
    global SPECIAL
    SPECIAL = {p: bmp(STRIPES) for p in pids}
    for p in solid:
        SPECIAL[p] = bmp(SOLID)
    for p in dark:
        SPECIAL[p] = bmp(DARK)


SPECIAL: dict[str, bytes] = {}


def cand(pid: str, typ: str = "video", h: int = 1920, w: int = 1080, duration: float = 10) -> Candidate:
    return Candidate(provider="pexels", provider_asset_id=pid, asset_type=typ, creator="C", source_url=f"page/{pid}",
                     download_url=f"dl://{pid}", thumb_url=f"thumb://{pid}", width=w, height=h, fps=30, duration=duration)


class FakeProvider2(FakeProvider):  # distinct thumbs per pid: a1 striped, a2 solid
    async def download_thumb(self, a):
        self.thumb_downloads.append(a.provider_asset_id)
        return thumb_for(a.provider_asset_id)


def assign_sync(brief, pieces, providers, notes: list):
    with mock.patch.object(assets, "get_providers", lambda: providers):
        assets.assign(brief, pieces, lambda stage, p: notes.append((stage, round(p, 2))))


def asset_row(pid: str) -> dict | None:
    with assets.connect() as conn:
        r = conn.execute("SELECT * FROM assets WHERE provider_asset_id = ?", (pid,)).fetchone()
    return dict(r) if r else None


def use_count(pid: str) -> int:
    with assets.connect() as conn:
        return conn.execute("SELECT count(*) FROM asset_usage u JOIN assets a ON a.id = u.asset_id "
                            "WHERE a.provider_asset_id = ?", (pid,)).fetchone()[0]


def piece_row(project_id: str, idx: int = 1, visual_type: str = "video") -> dict:
    content._insert(project_id, idx, f"angle {idx}", f"a quote for piece {idx}", {
        "plan": {"angle": f"angle {idx}", "visual_subject": "s", "visual_type": visual_type, "intensity": "low",
                 "narration_style": "calm"},
        "visual": {"preferred_type": visual_type, "search_query": "mountain runner", "secondary_query": "dawn trail",
                   "mood": "quiet"}})
    return content.pieces(project_id)[idx - 1]


class Hashing(unittest.TestCase):
    def test_identical_image_hashes_equal(self):
        self.assertEqual(assets.dhash(bmp(STRIPES)), assets.dhash(bmp(STRIPES)))

    def test_opposite_gradients_are_far_apart(self):
        self.assertGreater(assets.hamming(assets.dhash(bmp(STRIPES)), assets.dhash(bmp(INVERTED))), assets.SIMILAR_BITS)

    def test_stripes_and_solid_are_far_apart(self):
        self.assertGreater(assets.hamming(assets.dhash(bmp(STRIPES)), assets.dhash(bmp(SOLID))), assets.SIMILAR_BITS)

    def test_hash_is_hex16(self):
        self.assertEqual(len(assets.dhash(bmp(SOLID))), 16)
        int(assets.dhash(bmp(STRIPES)), 16)


class Selection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def setUp(self):
        with assets.connect() as conn:  # cooldown state is global, so every test starts from an empty library
            conn.execute("DELETE FROM asset_usage")
            conn.execute("DELETE FROM assets")
        settings.update(asset_cooldown_days=7)

    def test_assign_downloads_and_records(self):
        p = projects.create(BRIEF)
        make_thumbs("a1", "a2", solid=("a2",))
        prov = FakeProvider2([cand("a1", duration=12), cand("a2")])
        notes: list = []
        assign_sync(BRIEF, [piece_row(p["id"])], [prov], notes)
        self.assertEqual(prov.downloads, ["a1"])  # winner only; the second candidate is never fetched whole
        self.assertEqual(prov.thumb_downloads, ["a1", "a2"])  # thumbnails first (PRD §64)
        self.assertIn("Finding visual 1 of 1", notes[0][0])
        row = asset_row("a1")
        self.assertEqual((row["provider"], row["asset_type"], row["creator"], row["license"]),
                         ("pexels", "video", "C", "Test License"))
        self.assertEqual(use_count("a1"), 1)
        self.assertTrue((config.MEDIA_DIR / row["local_path"]).exists())
        self.assertTrue((config.MEDIA_DIR / row["thumb_path"]).exists())
        stored = content.pieces(p["id"])[0]["content"]
        self.assertEqual(stored["asset"]["id"], row["id"])
        self.assertNotIn("visual_error", stored)

    def test_second_piece_avoids_first_pick_even_without_history(self):
        p = projects.create(BRIEF)
        make_thumbs("a1", "a2", solid=("a2",))
        prov = FakeProvider2([cand("a1"), cand("a2")])
        assign_sync(BRIEF, [piece_row(p["id"], 1)], [prov], [])
        assign_sync(BRIEF, [piece_row(p["id"], 2)], [prov], [])
        picks = [content.pieces(p["id"])[i]["content"]["asset"]["id"] for i in (0, 1)]
        self.assertNotEqual(picks[0], picks[1])

    def test_exhausted_pool_falls_back_to_least_used(self):
        p = projects.create(BRIEF)
        make_thumbs("a1")
        prov = FakeProvider2([cand("a1")])
        for i in (1, 2):
            assign_sync(BRIEF, [piece_row(p["id"], i)], [prov], [])
        picks = [content.pieces(p["id"])[i]["content"]["asset"]["id"] for i in (0, 1)]
        self.assertEqual(picks[0], picks[1])  # only candidate: reused rather than failing
        self.assertEqual(use_count("a1"), 2)

    def test_similar_asset_cooled_out(self):
        p = projects.create(BRIEF)
        make_thumbs("a1")
        piece = piece_row(p["id"])
        with assets.connect() as conn:  # a striped asset like a1's thumb was used moments ago
            conn.execute("INSERT INTO assets (id, provider, provider_asset_id, asset_type, local_path, perceptual_hash) "
                         "VALUES ('db1', 'pexels', 'old1', 'video', 'assets/x.mp4', ?)", (assets.dhash(bmp(STRIPES)),))
            conn.execute("INSERT INTO asset_usage (asset_id, piece_id) VALUES ('db1', ?)", (piece["id"],))
        prov = FakeProvider2([cand("a1")])
        assign_sync(BRIEF, [piece], [prov], [])
        stored = content.pieces(p["id"])[0]["content"]
        self.assertNotIn("asset", stored)
        self.assertIn("No usable video", stored["visual_error"])
        self.assertEqual(prov.downloads, [])

    def test_different_looking_asset_passes_cooldown(self):
        p = projects.create(BRIEF)
        make_thumbs("a1", solid=("a1",))  # a1's thumb is solid: far from the used striped asset
        piece = piece_row(p["id"])
        with assets.connect() as conn:
            conn.execute("INSERT INTO assets (id, provider, provider_asset_id, asset_type, local_path, perceptual_hash) "
                         "VALUES ('db1', 'pexels', 'old1', 'video', 'assets/x.mp4', ?)", (assets.dhash(bmp(STRIPES)),))
            conn.execute("INSERT INTO asset_usage (asset_id, piece_id) VALUES ('db1', ?)", (piece["id"],))
        assign_sync(BRIEF, [piece], [FakeProvider2([cand("a1")])], [])
        self.assertIn("asset", content.pieces(p["id"])[0]["content"])

    def test_existing_library_asset_reused_without_downloads(self):
        p = projects.create(BRIEF)
        make_thumbs("a1")
        prov = FakeProvider2([cand("a1")])
        assign_sync(BRIEF, [piece_row(p["id"], 1)], [prov], [])
        self.assertEqual(prov.downloads, ["a1"])
        prov2 = FakeProvider2([cand("a1")])  # same candidate again: the library row must stand in
        assign_sync(BRIEF, [piece_row(p["id"], 2)], [prov2], [])
        self.assertEqual((prov2.downloads, prov2.thumb_downloads), ([], []))
        self.assertEqual(use_count("a1"), 2)

    def test_poor_quality_candidates_skipped(self):
        p = projects.create(BRIEF)
        make_thumbs("a1", "a2", dark=("a1",))  # near-black rank-1 asset loses to the healthy rank-2 asset
        prov = FakeProvider2([cand("a1"), cand("a2")])
        assign_sync(BRIEF, [piece_row(p["id"])], [prov], [])
        self.assertEqual(prov.downloads, ["a2"])

    def test_no_candidates_is_a_piece_error_not_a_crash(self):
        p = projects.create(BRIEF)
        assign_sync(BRIEF, [piece_row(p["id"])], [FakeProvider2([])], [])
        self.assertIn("No usable video", content.pieces(p["id"])[0]["content"]["visual_error"])

    def test_format_forces_type(self):
        p = projects.create(BRIEF)
        make_thumbs("a1")
        assign_sync({**BRIEF, "format": "image"}, [piece_row(p["id"])], [FakeProvider2([cand("a1", typ="video")])], [])
        self.assertIn("No usable image", content.pieces(p["id"])[0]["content"]["visual_error"])

    def test_unsuitable_candidates_skipped(self):
        p = projects.create(BRIEF)
        make_thumbs("u3")
        prov = FakeProvider2([cand("u1", w=1920, h=1080), cand("u2", duration=2), cand("u3")])
        assign_sync(BRIEF, [piece_row(p["id"])], [prov], [])
        self.assertEqual(prov.downloads, ["u3"])
        self.assertEqual(asset_row("u3")["height"], 1920)

    def test_skipped_honestly_without_keys(self):
        p = projects.create(BRIEF)
        notes: list = []
        with mock.patch.dict(config.SECRETS, {}, clear=True):
            assets.assign(BRIEF, [piece_row(p["id"])], lambda s, pr: notes.append(s))
        self.assertIn("Pexels or Unsplash key", notes[0])
        self.assertEqual(assets.list_assets(), [])


def run_job_with(providers, model, project_id) -> dict:
    with mock.patch.object(content, "get_model", lambda: model), \
            mock.patch.object(assets, "get_providers", lambda: providers), mock.patch.object(jobs, "emit"):
        job = jobs.start(project_id)
        for _ in range(300):
            job = jobs.get(job["id"])
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.02)
    raise AssertionError("job did not finish")


class JobIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def setUp(self):
        with assets.connect() as conn:
            conn.execute("DELETE FROM asset_usage")
            conn.execute("DELETE FROM assets")

    def test_full_job_writes_pieces_and_visuals(self):
        p = projects.create({**BRIEF, "quantity": 2})
        make_thumbs("a1", "a2", solid=("a2",))
        prov = FakeProvider2([cand("a1"), cand("a2"), cand("a3")])
        job = run_job_with([prov], FakeModel(["One quiet step at a time.", "The work is the way."]), p["id"])
        self.assertEqual(job["status"], "completed")
        pieces = content.pieces(p["id"])
        self.assertEqual([bool(x["content"].get("asset")) for x in pieces], [True, True])
        self.assertEqual(prov.downloads, ["a1", "a2"])
        rows = assets.list_assets()
        self.assertEqual([r["times_used"] for r in rows], [1, 1])
        self.assertEqual(projects.get(p["id"])["status"], "ready")


PEXELS_VIDEOS = {"videos": [{
    "id": 9, "width": 1080, "height": 1920, "url": "https://pexels.com/v/9", "duration": 12,
    "image": "https://img/9.jpg", "user": {"name": "Videographer"},
    "video_files": [
        {"file_type": "video/mp4", "width": 3840, "height": 2160, "fps": 30.0, "link": "https://f/4k"},
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "fps": 60.0, "link": "https://f/land"},
        {"file_type": "video/mp4", "width": 720, "height": 1280, "fps": 25.0, "link": "https://f/720"},
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "fps": 30.0, "link": "https://f/1080"},
        {"file_type": "video/webm", "width": 1080, "height": 1920, "fps": 30.0, "link": "https://f/webm"},
    ]}]}

PEXELS_PHOTOS = {"photos": [{
    "id": 4, "width": 4000, "height": 6000, "url": "https://pexels.com/p/4", "photographer": "Shooter",
    "src": {"large2x": "https://img/4@2x", "medium": "https://img/4m"}}]}

UNSPLASH = {"results": [{
    "id": "u1", "width": 3000, "height": 4500,
    "urls": {"small": "https://img/u1s"}, "links": {"html": "https://unsplash.com/p/u1",
                                                    "download_location": "https://unsplash.com/p/u1/download"},
    "user": {"name": "Snapper"}}]}


class Providers(unittest.TestCase):
    def test_pexels_video_picks_portrait_closest_to_target(self):
        def handler(request: httpx.Request):
            self.assertEqual(request.headers["Authorization"], "good-key")
            self.assertIn("/videos/search", str(request.url))
            return httpx.Response(200, json=PEXELS_VIDEOS)

        out = asyncio.run(PexelsProvider("good-key", transport=httpx.MockTransport(handler)).search_videos("waves", 8))
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0].download_url, out[0].fps, out[0].duration, out[0].creator),
                         ("https://f/1080", 30.0, 12.0, "Videographer"))

    def test_pexels_photos(self):
        def handler(request: httpx.Request):
            self.assertIn("/v1/search", str(request.url))
            return httpx.Response(200, json=PEXELS_PHOTOS)

        out = asyncio.run(PexelsProvider("k", transport=httpx.MockTransport(handler)).search_images("fog", 8))
        self.assertEqual((out[0].provider_asset_id, out[0].download_url, out[0].thumb_url, out[0].creator),
                         ("4", "https://img/4@2x", "https://img/4m", "Shooter"))

    def test_unsplash_photos_and_no_videos(self):
        def handler(request: httpx.Request):
            self.assertEqual(request.headers["Authorization"], "Client-ID u-key")
            return httpx.Response(200, json=UNSPLASH)

        p = UnsplashProvider("u-key", transport=httpx.MockTransport(handler))
        out = asyncio.run(p.search_images("calm", 8))
        self.assertEqual((out[0].provider_asset_id, out[0].download_url, out[0].thumb_url, out[0].creator),
                         ("u1", "https://unsplash.com/p/u1/download", "https://img/u1s", "Snapper"))
        self.assertEqual(asyncio.run(p.search_videos("calm", 8)), [])

    def test_unsplash_download_goes_through_download_location(self):
        def handler(request: httpx.Request):
            self.assertIn("/download", str(request.url))
            return httpx.Response(200, content=b"jpeg-bytes")

        p = UnsplashProvider("k", transport=httpx.MockTransport(handler))
        c = Candidate(provider="unsplash", provider_asset_id="u1", asset_type="image",
                      download_url="https://unsplash.com/p/u1/download", thumb_url="https://img/u1s",
                      width=3000, height=4500)
        self.assertEqual(asyncio.run(p.download(c)), b"jpeg-bytes")

    def test_auth_errors_are_human(self):
        for cls, label in ((PexelsProvider, "Pexels"), (UnsplashProvider, "Unsplash")):
            p = cls("bad", transport=httpx.MockTransport(lambda r: httpx.Response(401, text="nope")))
            with self.assertRaisesRegex(UserError, f"{label} authentication failed"):
                asyncio.run(p.search_images("x", 8))


if __name__ == "__main__":
    unittest.main()
