"""Voiced quote videos over footage clips, and the user's own Pexels/Unsplash links (owner 2026-11-12)."""
import asyncio
import io
import json
import os
import tempfile
import unittest
import uuid
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

from app import assets, database, projects, renders  # noqa: E402
from app.assets.providers import Candidate, PexelsProvider, UnsplashProvider  # noqa: E402
from app.errors import UserError  # noqa: E402


class FakePexels:
    name = "pexels"

    async def by_id(self, slug, kind):
        n = slug.rsplit("-", 1)[-1]
        return Candidate(provider="pexels", provider_asset_id=n, asset_type=kind, download_url=f"v{n}.mp4",
                         thumb_url=f"t{n}.jpg", width=1080, height=1920, duration=20)

    async def download_thumb(self, c):
        out = io.BytesIO()
        Image.new("RGB", (90, 160), (int(c.provider_asset_id) % 255, 40, 90)).save(out, "JPEG")
        return out.getvalue()


def option(key: str, query: str, phash: str) -> dict:
    return {"key": key, "queries": [query], "note": None, "score": 1.0, "used": 0, "phash": phash}


class VoicedClips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def test_backdrop_switches_the_search_to_footage(self):
        content = {"plan": {"visual_type": "image"}}
        self.assertEqual(assets._wanted({"format": "image_voiced"}, content), "image")
        self.assertEqual(assets._wanted({"format": "image_voiced", "backdrop": "clips"}, content), "video")

    def test_prepick_fills_five_clips_from_two_searches(self):
        # distinct looks (far-apart hashes) under only two queries: rounds over the queries fill the set
        opts = [option(f"p:{i}", "sea" if i % 2 else "fog", format(i * 0x0F0F0F0F0F0F0F0F % (1 << 64), "016x"))
                for i in range(1, 9)]
        self.assertEqual(len(assets._prepick(opts, ["sea", "fog"], 5, rounds=5)), 5)
        self.assertEqual(len(assets._prepick(opts, ["sea", "fog"], 5)), 2)  # narrated videos: one per search, as before

    def test_clips_cover_the_reveal_and_alternate_moves(self):
        pool = [{"local_path": "a.mp4", "asset_type": "video", "duration": 6.0},
                {"local_path": "b.mp4", "asset_type": "video", "duration": 2.0},
                {"local_path": "c.jpg", "asset_type": "image", "duration": None}]
        shots = renders._behind_words(pool, 12.0, True)
        span = sum(s["length"] for s in shots) - sum(s.get("tdur", 0) for s in shots)
        self.assertAlmostEqual(span, 12.0, places=3)
        self.assertTrue(all(s["dim"] for s in shots))
        self.assertGreater(len({round(s["length"], 2) for s in shots}), 2)  # a range, not one fixed length
        self.assertEqual([s["length"] for s in shots], [s["length"] for s in renders._behind_words(pool, 12.0, True)])  # seeded
        self.assertTrue(shots[1]["loop"])  # a 2 s clip in a ~2.8 s slot loops instead of running out
        self.assertEqual(shots[2]["motion"], "drift")  # the photo drifts like the photo version
        self.assertEqual({s["motion"] for s in renders._behind_words(pool[:1], 12.0, False)}, {None})

    def test_links_parse_and_bad_links_are_refused(self):
        self.assertEqual(assets.LINK.match("https://www.pexels.com/video/waves-on-rocks-1918465/").groups(),
                         ("pexels", "video", "waves-on-rocks-1918465"))
        with self.assertRaises(UserError):
            assets.add_links("no-such-piece", "https://example.com/photo/1")

    def test_several_links_at_once_grow_the_piece_and_play_first(self):
        p = projects.create({"topic": "patience", "tone": "stoic", "format": "image_voiced", "backdrop": "clips",
                             "quantity": 1, "platforms": ["tiktok"]})
        piece_id = uuid.uuid4().hex[:12]
        ai = [{"key": f"pexels:{9000 + i}", "queries": ["fog"], "note": None} for i in range(5)]
        review = {"want": 5, "type": "video", "options": ai, "picked": [o["key"] for o in ai]}
        with database.connect() as conn:
            conn.execute("INSERT INTO content_pieces (id, project_id, idx, status, angle, quote, content) "
                         "VALUES (?,?,?,?,?,?,?)", (piece_id, p["id"], 1, "written", "a", "q",
                                                     json.dumps({"review": review})))
        with mock.patch.object(assets, "get_providers", lambda: [FakePexels()]):
            r = assets.add_links(piece_id, "https://www.pexels.com/video/sea-11/, https://nope.example/x\n"
                                           "https://www.pexels.com/video/fog-12/")
            self.assertEqual([o["key"] for o in r["added"]], ["pexels:11", "pexels:12"])
            self.assertEqual(r["picked"][:2], ["pexels:11", "pexels:12"])  # yours first, in the order pasted
            self.assertEqual((r["want"], len(r["picked"])), (5, 5))  # two links fit the five clips already planned
            self.assertEqual([x["url"] for x in r["skipped"]], ["https://nope.example/x"])
            many = " ".join(f"https://www.pexels.com/video/clip-{n}/" for n in range(20, 26))
            r = assets.add_links(piece_id, many)
            self.assertEqual(r["want"], 8)  # eight of yours now: the piece grows to hold every one
            self.assertEqual(set(r["picked"]), {f"pexels:{n}" for n in (11, 12, *range(20, 26))})

    def test_pexels_and_unsplash_fetch_one_asset_by_its_link(self):
        def pexels(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/videos/videos/1918465":
                return httpx.Response(200, json={"id": 1918465, "url": "u", "image": "t.jpg", "duration": 9,
                                                 "user": {"name": "Ana"}, "video_files": [
                                                     {"file_type": "video/mp4", "width": 1080, "height": 1920,
                                                      "link": "v.mp4", "fps": 25}]})
            return httpx.Response(404, json={})
        c = asyncio.run(PexelsProvider("k", httpx.MockTransport(pexels)).by_id("waves-on-rocks-1918465", "video"))
        self.assertEqual((c.asset_type, c.provider_asset_id, c.download_url), ("video", "1918465", "v.mp4"))

        def unsplash(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/photos/XyZ12abCDeF":
                return httpx.Response(200, json={"id": "XyZ12abCDeF", "user": {"name": "Bo"}, "width": 3, "height": 4,
                                                 "links": {"html": "h", "download_location": "d"},
                                                 "urls": {"small": "s"}})
            return httpx.Response(404, json={})
        c = asyncio.run(UnsplashProvider("k", httpx.MockTransport(unsplash)).by_id("foggy-hills-XyZ12abCDeF", "image"))
        self.assertEqual(c.provider_asset_id, "XyZ12abCDeF")
        with self.assertRaises(UserError):  # Unsplash has no video
            asyncio.run(UnsplashProvider("k", httpx.MockTransport(unsplash)).by_id("x", "video"))
        json.dumps(c.model_dump())  # stored in the piece's review as JSON


    def _library_asset(self, kind: str, size=(90, 160), provider="pexels", pid=None) -> str:
        from app import config
        aid = uuid.uuid4().hex[:12]
        rel = f"assets/{aid}.{'mp4' if kind == 'video' else 'jpg'}"
        (config.MEDIA_DIR / "assets").mkdir(parents=True, exist_ok=True)
        (config.MEDIA_DIR / "thumbs").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (90, 120, 150)).save(config.MEDIA_DIR / rel.replace(".mp4", ".jpg"), "JPEG")
        Image.new("RGB", (60, 100), (90, 120, 150)).save(config.MEDIA_DIR / f"thumbs/{aid}.jpg", "JPEG")
        with database.connect() as conn:
            conn.execute("INSERT INTO assets (id, provider, provider_asset_id, asset_type, local_path, thumb_path, "
                         "brightness, saturation, contrast, perceptual_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (aid, provider, pid or aid, kind, rel.replace(".mp4", ".jpg") if kind == "image" else rel,
                          f"thumbs/{aid}.jpg", 0.4, 0.3, 0.5, "00ff00ff00ff00ff"))
        return aid

    def _piece(self, fmt="image_voiced", backdrop="clips", kind="video", want=5) -> str:
        p = projects.create({"topic": "patience", "tone": "stoic", "format": fmt, "backdrop": backdrop,
                             "quantity": 1, "platforms": ["tiktok"]})
        piece_id = uuid.uuid4().hex[:12]
        ai = [{"key": f"pexels:{8000 + i}", "queries": ["fog"], "note": None} for i in range(want)]
        with database.connect() as conn:
            conn.execute("INSERT INTO content_pieces (id, project_id, idx, status, angle, quote, content) "
                         "VALUES (?,?,?,?,?,?,?)", (piece_id, p["id"], 1, "written", "a", "q", json.dumps(
                             {"review": {"want": want, "type": kind, "options": ai,
                                         "picked": [o["key"] for o in ai]}})))
        return piece_id

    def test_library_items_are_reused_first_without_downloading(self):
        piece = self._piece()
        clip, photo = self._library_asset("video"), self._library_asset("image")
        r = assets.add_from_library(piece, [clip, photo])
        self.assertEqual(r["picked"][:2], [o["key"] for o in r["added"]])  # in the order ticked, ahead of the AI
        self.assertEqual([o["queries"] for o in r["added"]], [["your library"]] * 2)
        self.assertTrue(r["added"][0]["thumb"].startswith("thumbs/"))  # the library's own thumbnail, kept forever

    def test_a_photo_post_refuses_library_clips_with_a_reason(self):
        piece = self._piece(fmt="image_voiced", backdrop="photo", kind="image", want=1)
        clip, photo = self._library_asset("video"), self._library_asset("image")
        r = assets.add_from_library(piece, [clip, photo])
        self.assertEqual(len(r["added"]), 1)
        self.assertIn("video", r["skipped"][0]["reason"])

    def test_an_old_small_pexels_photo_is_fetched_full_size_when_reused(self):
        from app import config
        aid = self._library_asset("image", size=(731, 1300), pid="777")

        class Pexels:
            name = "pexels"

            async def by_id(self, slug, kind):
                return Candidate(provider="pexels", provider_asset_id=slug, asset_type=kind, download_url="u",
                                 thumb_url="t")

            async def download(self, c):
                out = io.BytesIO()
                Image.new("RGB", (1440, 2560), (1, 2, 3)).save(out, "JPEG")
                return out.getvalue()
        asyncio.run(assets._sharpen_old(aid, Pexels()))
        with database.connect() as conn:
            rel = conn.execute("SELECT local_path FROM assets WHERE id = ?", (aid,)).fetchone()[0]
        with Image.open(config.MEDIA_DIR / rel) as im:
            self.assertEqual(im.size, (1440, 2560))
        asyncio.run(assets._sharpen_old(aid, Pexels()))  # already full size: left alone

if __name__ == "__main__":
    unittest.main()
