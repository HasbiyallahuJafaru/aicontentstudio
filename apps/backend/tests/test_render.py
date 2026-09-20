"""Milestone 5: composition, TTS and the renderers. Uses the real Windows SAPI voices and the real ffmpeg binary
(both skipped automatically where unavailable); no network."""
import asyncio
import math
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from PIL import Image  # noqa: E402

from app import config, content, database, jobs, projects, render, renders, settings, tts  # noqa: E402
from app.errors import UserError  # noqa: E402

from tests.test_assets import FakeProvider2, cand, make_thumbs, run_job_with  # noqa: E402
from tests.test_content import BRIEF, FakeModel  # noqa: E402

PAL = {"text": "#FFFFFF", "overlay": "#18201E", "primary": "#53645F", "dark": "#18201E", "light": "#E5ECE8",
       "secondary": "#A7B4AD"}


def tone_wav(path, seconds=2.0, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * i / rate)))
                               for i in range(int(seconds * rate))))


class Composition(unittest.TestCase):
    def test_wrap_respects_width(self):
        font = render._font(72)
        lines = render.wrap("Nobody sees the early hours. Discipline begins when motivation ends. " * 3, font, 888)
        self.assertGreater(len(lines), 2)
        for line in lines:
            self.assertLessEqual(font.getlength(line), 888)

    def test_font_size_follows_quote_length(self):
        self.assertEqual(render.font_size("Show up before the feeling does.", 5)[0], 96)
        long_quote = ("Nobody sees the early hours and that is the whole point of the quiet work we do "
                      "when nobody is clapping for us at all.")
        self.assertLess(render.font_size(long_quote, 5)[0], 96)

    def test_placement_keeps_clear_of_the_subject(self):
        quote = "Discipline begins when motivation ends."
        left_subject = render.placement(quote, "left", "video")
        right_subject = render.placement(quote, "right", "video")
        center = render.placement(quote, "center", "video")
        font = render._font(left_subject["size"])
        width = font.getlength(left_subject["lines"][0])
        self.assertAlmostEqual(left_subject["positions"][0][0] + width, 1080 - render.MARGIN, delta=2)
        self.assertGreaterEqual(right_subject["positions"][0][0], render.MARGIN - 1)
        cw = font.getlength(center["lines"][0])
        self.assertAlmostEqual(center["positions"][0][0], (1080 - cw) / 2, delta=2)

    def test_escapes_filter_specials(self):
        self.assertEqual(render.esc("a:b\\c"), "a\\:b\\\\c")


class TTS(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows SAPI voices")
    def test_windows_tts_speaks(self):
        result = asyncio.run(tts.WindowsTTS().generate("Discipline begins when motivation ends.", "", 1.0))
        self.assertTrue(result.path.exists())
        self.assertGreater(result.duration, 0.5)

    def test_kokoro_without_model_is_human(self):
        settings.update(tts_provider="kokoro")
        try:
            with self.assertRaisesRegex(UserError, "not installed|not downloaded"):
                tts.get_tts()
        finally:
            settings.update(tts_provider="windows")


def make_source_video(path: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=2",
                    "-c:v", "libx264", "-preset", "ultrafast", path], check=True, timeout=60)


class Renderers(unittest.TestCase):
    """Tests run small and fast: 540x960 output, ~2s clips (PRD §49 makes resolution a setting)."""

    @classmethod
    def setUpClass(cls):
        database.migrate()
        if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
            raise unittest.SkipTest("ffmpeg not on PATH")
        cls.w, cls.h = 540, 960
        cls.src = config.MEDIA_DIR / "fixtures" / "src.mp4"
        cls.src.parent.mkdir(parents=True, exist_ok=True)
        make_source_video(str(cls.src))
        cls.narration = config.MEDIA_DIR / "fixtures" / "narration.wav"
        tone_wav(cls.narration, 1.2)
        cls.scrim_png = render.scrim(config.MEDIA_DIR / "fixtures" / "scrim.png", PAL["overlay"],
                                     cls.w, cls.h, (30, 190))
        cls.still = config.MEDIA_DIR / "fixtures" / "still.jpg"
        Image.new("RGB", (800, 1200), (40, 60, 50)).save(cls.still)
        cls.renderer = render.FFmpegRenderer(28, "128k", None, 0.15, cls.w, cls.h)

    def test_render_video_passes_validation(self):
        out = config.MEDIA_DIR / "renders" / "test" / "001-video.mp4"
        info = self.renderer.render_video(src=self.src, narration=self.narration, scrim_png=self.scrim_png,
                                          out=out, quote="Discipline begins when motivation ends.",
                                          subject_position="center", palette=PAL, src_fps=30, src_duration=2.0,
                                          still=False, progress=None)
        self.assertTrue(out.exists())
        self.assertAlmostEqual(info["duration"], 1.8, delta=1.0)
        self.assertAlmostEqual(info["fps"], 30.0, delta=1.0)

    def test_render_still_image_to_video(self):
        out = config.MEDIA_DIR / "renders" / "test" / "002-video.mp4"
        info = self.renderer.render_video(src=self.still, narration=self.narration, scrim_png=self.scrim_png, out=out,
                                          quote="The quiet work is the real work.", subject_position="left",
                                          palette=PAL, src_fps=0, src_duration=0, still=True, progress=None)
        self.assertAlmostEqual(info["fps"], 60.0, delta=1.0)

    def test_render_video_with_look_blur_parallax_and_subtitles(self):
        """The Create page's look effects + subtitles: exercises the whole filter graph syntax."""
        from app.clipper.captions import captions as ass_captions
        subs = config.MEDIA_DIR / "fixtures" / "subs.ass"
        subs.write_text(ass_captions([{"word": "Hello", "start": 0.0, "end": 1.0},
                                      {"word": "world.", "start": 1.0, "end": 1.8}], 0.0, 2.0, self.w, self.h),
                        encoding="utf-8")
        out = config.MEDIA_DIR / "renders" / "test" / "003-video.mp4"
        info = self.renderer.render_video(src=self.src, narration=self.narration, out=out,
                                          subject_position="center", src_fps=30, src_duration=14.0,
                                          still=False, progress=None, out_fps=60, look="warm",
                                          blur_background=True, parallax=True, subtitles=subs)
        self.assertAlmostEqual(info["fps"], 60.0, delta=1.0)

    def test_render_image_output(self):
        out = config.MEDIA_DIR / "renders" / "test" / "001-image.jpg"
        self.renderer.render_image(src=self.still, out=out, quote="Show up before the feeling does.",
                                   subject_position="left", palette=PAL)
        with Image.open(out) as check:
            self.assertEqual((check.size, check.format), ((render.IMAGE_W, render.IMAGE_H), "JPEG"))


class RenderJob(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def test_full_render_job(self):
        settings.update(render_width=540, render_height=960)  # small and fast, like the other tests here
        p = projects.create({**BRIEF, "quantity": 1})
        with database.connect() as conn:  # earlier tests' usage must not cool this test's candidate out
            conn.execute("DELETE FROM asset_usage")
        make_thumbs("a1")
        run_job_with([FakeProvider2([cand("a1")])],
                     FakeModel(["Frame the quiet hours and press render."]), p["id"])

        # swap the fake downloaded bytes for a real video file so ffmpeg has something to render
        piece = content.pieces(p["id"])[0]
        with database.connect() as conn:
            row = conn.execute("SELECT id, local_path FROM assets WHERE id = ?",
                               (piece["content"]["asset"]["id"],)).fetchone()
            make_source_video(str(config.MEDIA_DIR / row["local_path"]))
            conn.execute("UPDATE assets SET fps = 30, duration = 2.0, subject_position = 'center' WHERE id = ?",
                         (row["id"],))

        class FakeTTS(tts.TTSProvider):
            name = "fake"

            def __init__(self):
                self.texts = []

            async def generate(self, text, voice, speed):
                self.texts.append(text)
                path = config.MEDIA_DIR / "audio" / f"fake-{len(self.texts)}.wav"
                path.parent.mkdir(parents=True, exist_ok=True)
                tone_wav(path, 2.0)
                return tts.AudioResult(path)

        with mock.patch.object(renders.tts, "get_tts", lambda: FakeTTS()), mock.patch.object(jobs, "emit"):
            job = jobs.start(p["id"], kind="render")
            for _ in range(400):
                job = jobs.get(job["id"])
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(0.05)
        self.assertEqual(job["status"], "completed")
        pieces = content.pieces(p["id"])
        self.assertEqual(pieces[0]["status"], "ready")
        rows = renders.list_(p["id"])
        self.assertEqual([r["kind"] for r in rows], ["video"])
        self.assertTrue((config.MEDIA_DIR / rows[0]["local_path"]).exists())
        self.assertNotIn("render_error", pieces[0]["content"])


if __name__ == "__main__":
    unittest.main()
