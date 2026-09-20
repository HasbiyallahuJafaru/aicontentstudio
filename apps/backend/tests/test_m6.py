"""Milestone 6: per-component regeneration, approval, queue and export (PRD §43, §46, §47, §68-73)."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app import config, content, database, export, jobs, platforms, projects, queue, renders, settings  # noqa: E402
from app.errors import UserError  # noqa: E402

from tests.test_assets import FakeProvider2, cand, make_thumbs, run_job_with  # noqa: E402
from tests.test_content import BRIEF, FakeModel  # noqa: E402
from tests.test_render import make_source_video, tone_wav  # noqa: E402


class Platforms(unittest.TestCase):
    META = {"title": "t", "description": "d", "caption": "c", "hashtags": ["a", "#b"], "keywords": ["k"],
            "alt_text": "alt"}

    def test_youtube_shorts_adapts_title_and_description(self):
        out = platforms.adapt("youtube_shorts", {**self.META, "title": "x" * 120}, {"video_9x16.mp4": "v.mp4"})
        self.assertLessEqual(len(out["title"]), 100)
        self.assertIn("#a #b", out["description"])
        self.assertEqual(out["file"], "video_9x16.mp4")
        self.assertIn("suggested_time", out)

    def test_instagram_captions_within_limit(self):
        meta = {**self.META, "caption": "c" * 3000}
        files = {"video_9x16.mp4": "v.mp4", "image_4x5.jpg": "i.jpg"}
        for platform in ("instagram_reels", "instagram_feed"):
            out = platforms.adapt(platform, meta, files)
            self.assertLessEqual(len(out["caption"]), platforms.IG_CAPTION_MAX)

    def test_feed_prefers_the_image(self):
        out = platforms.adapt("instagram_feed", self.META, {"video_9x16.mp4": "v.mp4", "image_4x5.jpg": "i.jpg"})
        self.assertEqual(out["file"], "image_4x5.jpg")

    def test_missing_render_is_reported_not_hidden(self):
        with self.assertRaises(UserError):
            platforms.adapt("instagram_feed", self.META, {"video_9x16.mp4": "v.mp4"})


class Regenerate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()
        cls.p = projects.create({**BRIEF, "quantity": 1})
        with database.connect() as conn:  # other modules' usage must not cool this test's candidates out
            conn.execute("DELETE FROM asset_usage")
        make_thumbs("a1", solid=("a2",))
        run_job_with([FakeProvider2([cand("a1")])], FakeModel(["Hold the line when it hurts."]), cls.p["id"])

    def piece(self):
        return content.pieces(self.p["id"])[0]

    def test_1_regenerate_narration_keeps_everything_else(self):
        before = self.piece()
        with mock.patch.object(content, "get_model",
                               lambda: FakeModel(["Step again in the wrong direction."])):
            fresh = content.regenerate(before["id"], "narration")
        self.assertNotEqual(fresh["content"]["narration"]["text"], before["content"]["narration"]["text"])
        self.assertEqual(fresh["content"]["quote"], before["content"]["quote"])
        self.assertEqual(fresh["content"]["asset"], before["content"]["asset"])
        self.assertEqual(fresh["status"], "written")  # renders are stale now, piece waits for a new render

    def test_2_regenerate_visual_picks_a_different_asset(self):
        before = self.piece()
        with database.connect() as conn:  # wipe so the fresh candidate isn't cooled out by earlier tests
            conn.execute("DELETE FROM asset_usage")
        with mock.patch.object(content.assets, "get_providers", lambda: [FakeProvider2([cand("a2")])]):
            fresh = content.regenerate(before["id"], "visual")
        self.assertNotEqual(fresh["content"]["asset"]["id"], before["content"]["asset"]["id"])
        self.assertNotEqual(fresh["content"]["palette"], before["content"]["palette"])  # §43: reanalyzed -> new palette

    def test_3_unknown_scope_and_failed_piece_are_rejected(self):
        with self.assertRaisesRegex(UserError, "Unknown"):
            content.regenerate(self.piece()["id"], "everything")
        with database.connect() as conn:
            conn.execute("UPDATE content_pieces SET status = 'failed' WHERE project_id = ?", (self.p["id"],))
        with self.assertRaisesRegex(UserError, "failed"):
            content.regenerate(self.piece()["id"], "quote")

    def test_4_approve_needs_a_render_first(self):
        with database.connect() as conn:  # undo the failed status test_3 left behind
            conn.execute("UPDATE content_pieces SET status = 'written' WHERE project_id = ?", (self.p["id"],))
        piece = self.piece()
        with self.assertRaisesRegex(UserError, "rendered"):
            content.approve(piece["id"])
        with database.connect() as conn:
            conn.execute("UPDATE content_pieces SET status = 'ready' WHERE id = ?", (piece["id"],))
        self.assertEqual(content.approve(piece["id"])["status"], "approved")


class Export(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()
        settings.update(render_width=540, render_height=960)
        cls.p = projects.create({**BRIEF, "quantity": 1})
        with database.connect() as conn:
            conn.execute("DELETE FROM asset_usage")
        make_thumbs("a1")
        run_job_with([FakeProvider2([cand("a1")])], FakeModel(["Export the quiet work today."]), cls.p["id"])
        piece = content.pieces(cls.p["id"])[0]
        with database.connect() as conn:
            row = conn.execute("SELECT id, local_path FROM assets WHERE id = ?",
                               (piece["content"]["asset"]["id"],)).fetchone()
            make_source_video(str(config.MEDIA_DIR / row["local_path"]))
            conn.execute("UPDATE assets SET fps = 30, duration = 2.0, subject_position = 'center' WHERE id = ?",
                         (row["id"],))

        class FakeTTS:
            name = "fake"

            async def generate(self, text, voice, speed):
                from app.tts import AudioResult
                path = config.MEDIA_DIR / "audio" / "fake-export.wav"
                path.parent.mkdir(parents=True, exist_ok=True)
                tone_wav(path, 1.2)
                return AudioResult(path)

        with mock.patch.object(renders.tts, "get_tts", lambda: FakeTTS()), mock.patch.object(jobs, "emit"):
            job = jobs.start(cls.p["id"], kind="render")
            for _ in range(400):
                job = jobs.get(job["id"])
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(0.05)
        cls.render_job = job

    def test_1_render_job_readied_the_piece(self):
        self.assertEqual(self.render_job["status"], "completed")
        self.assertEqual(content.pieces(self.p["id"])[0]["status"], "ready")

    def test_2_export_produces_the_prd_folder(self):
        summary = export.export_project(self.p["id"])
        piece = content.pieces(self.p["id"])[0]
        self.assertEqual(piece["status"], "exported")
        run = sorted(p for p in (config.DATA_DIR / "exports").rglob("001_*") if p.is_dir())[-1]
        names = {f.name for f in run.iterdir()}
        self.assertIn("video_9x16.mp4", names)
        self.assertIn("thumbnail.jpg", names)
        self.assertIn("caption.txt", names)
        self.assertIn("metadata.json", names)
        meta = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["platforms"]["tiktok"]["file"], "video_9x16.mp4")
        self.assertEqual(meta["theme"], "discipline")
        runs = export.list_()
        self.assertEqual(runs[0]["pieces"], 1)
        self.assertTrue((config.DATA_DIR / runs[0]["dir"]).exists())

    def test_3_queue_lists_pieces_and_jobs(self):
        data = queue.list_()
        self.assertTrue(any(p["project_id"] == self.p["id"] for p in data["pieces"]))
        self.assertTrue(any(j["kind"] == "render" for j in data["jobs"]))
        self.assertIn("project", data["pieces"][0])
        self.assertIn("renders", data["pieces"][0])


if __name__ == "__main__":
    unittest.main()
