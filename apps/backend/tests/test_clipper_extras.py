"""What came over from ClipperAi around the engine (2026-11-08): clip copy editing, the export spreadsheet, the
link preview before download, the plain downloader and the calendar's plan step. No network: HTTP and yt-dlp are
faked."""
import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

import yt_dlp  # noqa: E402

from app import clips, config, database, downloader, export, projects  # noqa: E402
from app.clipper import preview  # noqa: E402
from app.database import connect  # noqa: E402
from app.errors import UserError  # noqa: E402
from app.publish import posts, zernio  # noqa: E402

NETWORKS = ["tiktok", "instagram", "youtube", "linkedin", "facebook", "x"]


def setUpModule():
    database.migrate()


def clip_project(name="Extras talk", status="ready") -> tuple[dict, str]:
    src = config.MEDIA_DIR / "fixtures" / "extras-src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"source")
    p = projects.create({"kind": "clip", "source": str(src)})
    with connect() as conn:
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, p["id"]))
    folder = config.MEDIA_DIR / "clips" / p["id"]
    folder.mkdir(parents=True, exist_ok=True)
    for ext in ("mp4", "jpg", "ass"):
        (folder / f"clip01.{ext}").write_bytes(b"x")
    cid = f"c{p['id']}"
    with connect() as conn:
        conn.execute("INSERT INTO clips (id, project_id, idx, start_at, end_at, score, reason, hook, title, "
                     "description, hashtags, posts, status, video_path, cover_path) "
                     "VALUES (?, ?, 1, 12.345, 40.5, 88, 'why', 'the hook', 'Café talk', 'desc', '[\"#a\"]', ?, ?, ?, ?)",
                     (cid, p["id"], json.dumps({n: f"copy {n}" for n in NETWORKS}), status,
                      f"clips/{p['id']}/clip01.mp4", f"clips/{p['id']}/clip01.jpg"))
    return projects.get(p["id"]), cid


class EditCopy(unittest.TestCase):
    def test_edit_merges_posts_and_keeps_omitted_fields(self):
        _, cid = clip_project()
        c = clips.update(cid, title="New title", hashtags=[" #one ", "", "#two"], posts={"x": "short x post"})
        self.assertEqual(c["title"], "New title")
        self.assertEqual(c["hook"], "the hook")  # left out: unchanged
        self.assertEqual(c["hashtags"], ["#one", "#two"])
        self.assertEqual(c["posts"]["x"], "short x post")
        self.assertEqual(c["posts"]["tiktok"], "copy tiktok")  # other platforms keep their copy

    def test_over_limit_is_refused_not_trimmed(self):
        p, cid = clip_project()
        with self.assertRaisesRegex(UserError, "X post is 281 characters long; X allows 280"):
            clips.update(cid, posts={"x": "a" * 281})
        with self.assertRaisesRegex(UserError, "Unknown platform"):
            clips.update(cid, posts={"myspace": "hi"})
        self.assertEqual(clips.list_(p["id"])[0]["posts"]["x"], "copy x")  # nothing was saved

    def test_missing_clip(self):
        with self.assertRaisesRegex(UserError, "no longer exists"):
            clips.update("nope", title="t")


class ExportSheet(unittest.TestCase):
    def test_clip_export_writes_csv_and_json_and_delete_removes_them(self):
        p, _ = clip_project(name="Sheet talk")
        result = export.export_project(p["id"])
        root = Path(result["dir"])
        sheet = root / "sheet-talk_clips.csv"
        raw = sheet.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))  # BOM: Excel reads UTF-8
        rows = list(csv.DictReader(sheet.read_text(encoding="utf-8-sig").splitlines()))
        self.assertEqual(rows[0]["title"], "Café talk")
        self.assertEqual(rows[0]["x"], "copy x")
        self.assertEqual(rows[0]["start_s"], "12.35")
        self.assertEqual(list(rows[0])[:5], ["idx", "title", "hook", "description", "hashtags"])
        self.assertEqual(json.loads((root / "sheet-talk_clips.json").read_text(encoding="utf-8"))[0]["hashtags"], "#a")
        with connect() as conn:
            eid = conn.execute("SELECT id FROM exports WHERE project_id = ?", (p["id"],)).fetchone()["id"]
        export.delete(eid)
        self.assertFalse(sheet.exists())


class FakeResponse:
    def __init__(self, body=None, content=b"", ctype="application/json"):
        self._body, self.content, self.headers, self.is_success = body, content, {"content-type": ctype}, True

    def raise_for_status(self):
        return self

    def json(self):
        return self._body


class FakeClient:
    calls: list = []

    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params=None):
        FakeClient.calls.append(url)
        if url == "https://www.youtube.com/oembed":
            return FakeResponse({"title": "The real video name", "thumbnail_url": "https://i.ytimg.com/vi/x/hq.jpg"})
        return FakeResponse(content=b"\xff\xd8jpeg", ctype="image/jpeg")


class LinkPreview(unittest.TestCase):
    def test_endpoint_matches_hosts_and_subdomains(self):
        self.assertEqual(preview.endpoint("https://www.youtube.com/watch?v=abc"), "https://www.youtube.com/oembed")
        self.assertEqual(preview.endpoint("https://m.youtube.com/watch?v=abc"), "https://www.youtube.com/oembed")
        self.assertIsNone(preview.endpoint("https://notyoutube.com/x"))
        self.assertIsNone(preview.endpoint("https://example.com/video"))

    def test_fetch_names_project_and_stores_thumbnail(self):
        with mock.patch.object(preview, "start"):  # create without the background thread, then run it inline
            p = projects.create({"kind": "clip", "source": "https://www.youtube.com/watch?v=abc123"})
        with mock.patch.object(preview.httpx, "Client", FakeClient):
            preview.fetch(p["id"], "https://www.youtube.com/watch?v=abc123", p["name"])
        got = projects.get(p["id"])
        self.assertEqual(got["name"], "The real video name")
        self.assertEqual(got["brief"]["thumb"], f"clipwork/thumbs/{p['id']}.jpg")
        self.assertTrue((config.MEDIA_DIR / got["brief"]["thumb"]).is_file())
        cover = next(r["cover"] for r in projects.list_() if r["id"] == p["id"])
        self.assertEqual(cover, got["brief"]["thumb"])  # stands in as the cover until clips exist
        projects.delete(p["id"])
        self.assertFalse((config.MEDIA_DIR / got["brief"]["thumb"]).exists())

    def test_fetch_never_overrides_a_name_set_meanwhile(self):
        with mock.patch.object(preview, "start"):
            p = projects.create({"kind": "clip", "source": "https://youtu.be/abc123"})
        with connect() as conn:
            conn.execute("UPDATE projects SET name = 'Named by the download' WHERE id = ?", (p["id"],))
        with mock.patch.object(preview.httpx, "Client", FakeClient):
            preview.fetch(p["id"], "https://youtu.be/abc123", p["name"])
        self.assertEqual(projects.get(p["id"])["name"], "Named by the download")

    def test_create_ignores_a_thumb_passed_in(self):
        src = config.MEDIA_DIR / "fixtures" / "extras-src.mp4"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"source")
        p = projects.create({"kind": "clip", "source": str(src), "thumb": "../../secret.jpg"})
        self.assertNotIn("thumb", p["brief"])


class FakeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, url):
        hook = self.opts["progress_hooks"][0]
        hook({"downloaded_bytes": 50, "total_bytes": 100})
        if "blocked" in url:
            raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
        path = Path(tempfile.mkdtemp()) / "My video [abc].mp4"
        path.write_bytes(b"v")
        return {"title": "My video", "requested_downloads": [{"filepath": str(path)}]}


class PlainDownloader(unittest.TestCase):
    def test_rejects_non_links(self):
        with self.assertRaisesRegex(UserError, "video link"):
            downloader.start("C:/videos/a.mp4")
        with self.assertRaisesRegex(UserError, "no longer tracked"):
            downloader.status("missing")

    def test_download_reports_ready_with_its_file(self):
        with mock.patch.object(downloader.yt_dlp, "YoutubeDL", FakeYDL), \
                mock.patch.object(downloader, "FOLDER", Path(tempfile.mkdtemp())), \
                mock.patch.object(downloader.threading, "Thread") as thread:
            token = downloader.start("https://youtu.be/abc")["token"]
            downloader._work(token, "https://youtu.be/abc")  # what the thread would run
        thread.assert_called_once()
        s = downloader.status(token)
        self.assertEqual((s["status"], s["progress"], s["title"]), ("ready", 100, "My video"))
        self.assertTrue(Path(s["path"]).is_file())

    def test_bot_check_reads_as_words(self):
        with mock.patch.object(downloader.yt_dlp, "YoutubeDL", FakeYDL), \
                mock.patch.object(downloader, "FOLDER", Path(tempfile.mkdtemp())), \
                mock.patch.object(downloader.threading, "Thread"):
            token = downloader.start("https://youtu.be/blocked")["token"]
            downloader._work(token, "https://youtu.be/blocked")
        s = downloader.status(token)
        self.assertEqual(s["status"], "error")
        self.assertIn("not a bot", s["error"]["message"])


if __name__ == "__main__":
    unittest.main()
