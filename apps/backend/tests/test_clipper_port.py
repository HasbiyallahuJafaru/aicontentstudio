"""Milestone 7 Phase B: the ClipperAi engine port. Pure engine logic (snap, parsing, stitching, captions,
shots, post caps) plus real-ffmpeg renders on lavfi fixtures and a full clip job through the shared job system.
No network: Groq/DeepSeek are faked at their seams."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from pydantic import ValidationError  # noqa: E402

from app import clips as clips_app  # noqa: E402
from app import config, database, export, jobs, projects  # noqa: E402
from app.clipper import select, transcribe  # noqa: E402
from app.clipper.captions import captions  # noqa: E402
from app.clipper.crop import shots  # noqa: E402
from app.clipper.render_clip import ORIENTATIONS, render  # noqa: E402
from app.clipper.select import LIMITS, Moment, Posts, fits, parse_moments, parse_picks, snap  # noqa: E402
from app.clipper.transcribe import CHUNK, stitch  # noqa: E402
from app.errors import UserError  # noqa: E402


class Snapping(unittest.TestCase):
    words = [{"word": "a", "start": 0.0, "end": 0.4}, {"word": "b", "start": 0.5, "end": 1.0},
             {"word": "c", "start": 1.1, "end": 1.6}]
    sentences = [{"word": "One.", "start": 0.0, "end": 0.4}, {"word": "Two", "start": 0.5, "end": 1.0},
                 {"word": "words.", "start": 1.1, "end": 1.6}, {"word": "Next", "start": 2.0, "end": 2.4},
                 {"word": "one.", "start": 2.5, "end": 2.9}]

    def test_mid_word_cuts_widen_to_whole_words(self):
        self.assertEqual(snap(0.7, 1.3, self.words), (0.5, 1.6))

    def test_gap_cuts_land_on_neighbouring_word_edges(self):
        self.assertEqual(snap(0.45, 1.05, self.words), (0.5, 1.0))

    def test_no_word_timings_unchanged(self):
        self.assertEqual(snap(5, 6, []), (5, 6))

    def test_mid_sentence_cuts_widen_to_sentence_boundaries(self):
        self.assertEqual(snap(0.7, 1.3, self.sentences), (0.5, 1.6))

    def test_cuts_inside_last_sentence_widen_to_its_edges(self):
        self.assertEqual(snap(2.1, 2.85, self.sentences), (2.0, 2.9))


class PassOne(unittest.TestCase):
    """Invalid moments dropped, overlap keeps the higher score, result is chronological."""

    def test_filters_and_orders(self):
        moment = '{{"start": {}, "end": {}, "score": {}, "reason": "{}"}}'
        content = '{"moments": [' + ",".join([moment.format(300, 340, 70, "later"), moment.format(10, 50, 90, "t"),
                                              moment.format(100, 400, 80, "too long"), moment.format(590, 640, 70, "past end"),
                                              moment.format(30, 70, 95, "overlaps t")]) + "]}"
        self.assertEqual([m.reason for m in parse_moments(content, duration=600, min_len=30, max_len=60)],
                         ["overlaps t", "later"])

    def test_bad_output_rejected(self):
        for bad in ["", "not json", '{"moments": [{"start": 1}]}']:
            with self.assertRaises(ValidationError):
                parse_moments(bad, 600, 30, 60)
        with self.assertRaises(ValueError):
            parse_moments('{"moments": []}', 600, 30, 60)


class PassTwo(unittest.TestCase):
    """Timestamps come from pass 1, unknown/duplicate ids ignored, capped at n, trims guarded."""

    @classmethod
    def setUpClass(cls):
        cls.moments = [Moment(start=10, end=50, score=90, reason="r0"), Moment(start=100, end=140, score=80, reason="r1")]

    def pick(self, i, title):
        posts = dict.fromkeys(["tiktok", "instagram", "youtube", "linkedin", "facebook", "x"], "copy")
        return {"id": i, "score": 9, "hook": "h", "title": title, "description": "d", "hashtags": ["#a"], "posts": posts}

    def test_ids_and_ordering(self):
        content = json.dumps({"clips": [self.pick(1, "one"), self.pick(7, "ghost"),
                                        self.pick(1, "dupe"), self.pick(0, "zero")]})
        clips = parse_picks(content, self.moments, n=5)
        self.assertEqual([(c.title, c.start, c.reason) for c in clips], [("one", 100, "r1"), ("zero", 10, "r0")])
        self.assertEqual(len(parse_picks(content, self.moments, n=1)), 1)

    def test_trims(self):
        trim = lambda start, end: json.dumps({"clips": [self.pick(0, "t") | {"start": start, "end": end}]})
        ok = parse_picks(trim(15, 45), self.moments, 5)[0]
        self.assertEqual((ok.start, ok.end), (15, 45))
        for start, end in [(5, 45), (15, 55), (35, 45)]:  # before the candidate, past it, too short
            self.assertEqual(parse_picks(trim(start, end), self.moments, 5, min_len=30, max_len=60)[0].start, 10,
                             (start, end))

    def test_pick_without_every_platform_post_rejected(self):
        bad = json.dumps({"clips": [self.pick(0, "no posts") | {"posts": {"tiktok": "only one"}}]})
        with self.assertRaises(ValidationError):
            parse_picks(bad, self.moments, 5)


class Stitching(unittest.TestCase):
    def test_chunk_two_starts_at_seam_and_rehears_the_tail(self):
        t = {"language": None, "segments": [], "words": []}
        w = lambda text, s, e: {"word": text, "start": s, "end": e}
        stitch(t, [], [w("before", 590, 599.7), w("across", 599.8, 600.4), w("overlap", 600.5, 601)], 0, last=False)
        stitch(t, [], [w("cross", 0.0, 0.4), w("overlap", 0.5, 1.0), w("next", 1.2, 1.5)], CHUNK, last=True)
        self.assertEqual([(x["word"], x["start"]) for x in t["words"]],
                         [("before", 590), ("across", 599.8), ("overlap", 600.5), ("next", 601.2)], t["words"])

    def test_every_audio_chunk_is_a_standalone_file(self):
        """Regression: a chunk whose header claims the whole stream's length makes Groq return 500."""
        if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
            self.skipTest("ffmpeg not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tone.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=25", str(src)],
                           check=True, timeout=60)
            config.SECRETS["GROQ_API_KEY"] = "test"
            calls, durations = [], []

            def fake_post(url, headers, verify, chunk):
                durations.append(transcribe.duration_of(Path(chunk)))
                calls.append(chunk)
                return {"language": "en", "segments": [], "words": []}

            real_chunk, real_overlap = transcribe.CHUNK, transcribe.OVERLAP
            transcribe.CHUNK, transcribe.OVERLAP = 10, 2
            try:
                with mock.patch.object(transcribe, "_post", fake_post):
                    transcribe.transcribe(src, Path(tmp))
            finally:
                transcribe.CHUNK, transcribe.OVERLAP = real_chunk, real_overlap
                config.SECRETS.pop("GROQ_API_KEY", None)
            self.assertEqual([round(d) for d in durations], [12, 12, 5], durations)


class PostCaps(unittest.TestCase):
    def test_overlong_posts_trimmed_on_word_boundary_not_rejected(self):
        long = Posts(tiktok="a" * 3000, instagram="ok", youtube="y", linkedin="l", facebook="f", x="word " * 200)
        self.assertEqual(len(long.tiktok), LIMITS["tiktok"])
        self.assertEqual(long.instagram, "ok")
        self.assertLessEqual(len(long.x), LIMITS["x"])
        self.assertFalse(long.x.endswith(" "))
        self.assertEqual(long.x.split()[-1], "word")

    def test_fits_passthrough(self):
        self.assertEqual(fits("short", 280), "short")


class Captions(unittest.TestCase):
    def test_groups_highlight_and_escapes(self):
        ass = captions([{"word": "Most", "start": 10.0, "end": 10.3}, {"word": "companies", "start": 10.3, "end": 10.9},
                        {"word": "fail.", "start": 11.0, "end": 11.4}, {"word": "{Why?}", "start": 12.5, "end": 12.9},
                        {"word": "outside", "start": 30.0, "end": 30.5}], start=9.9, end=20)
        events = [line for line in ass.splitlines() if line.startswith("Dialogue")]
        self.assertNotIn("Hook", ass)
        self.assertEqual(events[0], "Dialogue: 0,0:00:00.10,0:00:00.40,Caption,,0,0,0,,{\\c&H0000E6FF&}Most{\\r} companies")
        self.assertEqual(events[1], "Dialogue: 0,0:00:00.40,0:00:01.10,Caption,,0,0,0,,Most {\\c&H0000E6FF&}companies{\\r}",
                         "18-char line limit splits off 'fail.'")
        self.assertEqual(events[2].split(",")[2], "0:00:02.00", "before a pause, the last word lingers 0.5s")
        self.assertTrue(events[3].endswith(",{\\c&H0000E6FF&}(Why?){\\r}"), "braces escaped")
        self.assertEqual(len(events), 4, "out-of-range word dropped")


class ShotDetection(unittest.TestCase):
    def test_jitter_then_move_is_two_steady_shots(self):
        xs = [400, 410, 395, 1400, 405, 400, 1400, 1395, 1410, 1405]
        self.assertEqual(shots(xs, deadzone=120), [(0, 402.5), (6, 1402.5)], shots(xs, 120))
        self.assertEqual(shots([500.0], 120), [(0, 500.0)])


def make_talking_head(path: str, seconds: int = 3) -> None:
    """A gray clip with a tone track: renders exercise the whole ffmpeg path without network."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=640x360:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=duration={seconds}", "-shortest", path], check=True, timeout=60)


class ClipRender(unittest.TestCase):
    """Captions burned by default, left out when asked; the caption file either way; every orientation sized."""

    @classmethod
    def setUpClass(cls):
        if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
            raise unittest.SkipTest("ffmpeg not on PATH")

    def test_burn_toggle_changes_the_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "talk.mp4"
            make_talking_head(str(src))
            words = [{"word": "HELLO", "start": 0.2, "end": 2.8}]
            frames = {}
            for burn in (True, False):
                out = Path(tmp) / f"clip-{burn}.mp4"
                render(src, 0, 3, out, words, burn=burn)
                self.assertTrue(out.exists() and out.with_suffix(".jpg").exists())
                self.assertIn("HELLO", out.with_suffix(".ass").read_text(encoding="utf-8"))
                frames[burn] = subprocess.run(
                    ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(out), "-frames:v", "1", "-f", "rawvideo",
                     "-pix_fmt", "gray", "-"], check=True, capture_output=True, timeout=60).stdout
            changed = sum(a != b for a, b in zip(frames[True], frames[False]))
            self.assertGreater(changed, 1000, f"burned captions must change the picture ({changed} pixels differ)")
            self.assertLessEqual(len(set(frames[False])), 3, "without captions the gray test picture stays plain")

    def test_orientations_render_their_own_size_and_playres(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "wide.mp4"
            make_talking_head(str(src), 2)
            for name, ((_, _), (w, h)) in ORIENTATIONS.items():
                out = Path(tmp) / f"clip-{name.replace(':', 'x')}.mp4"
                render(src, 0, 2, out, [{"word": "HELLO", "start": 0.2, "end": 1.8}], orientation=name)
                probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                        "stream=width,height", "-of", "json", str(out)], check=True,
                                       capture_output=True, timeout=60).stdout
                size = json.loads(probe)["streams"][0]
                self.assertEqual((size["width"], size["height"]), (w, h), name)
                caption_file = out.with_suffix(".ass").read_text(encoding="utf-8")
                self.assertIn(f"PlayResX: {w}", caption_file)
                self.assertIn(f"PlayResY: {h}", caption_file)


def fake_transcript(seconds: float) -> dict:
    words = [{"word": w, "start": 0.2 + i * 0.5, "end": 0.6 + i * 0.5}
             for i, w in enumerate(["One.", "Two.", "Three.", "Four."])]
    words = [w for w in words if w["start"] < seconds]
    return {"language": "en", "words": words,
            "segments": [{"start": 0.0, "end": words[-1]["end"], "text": " ".join(w["word"] for w in words)}]}


def one_clip():
    return select.Clip(start=0.2, end=1.6, score=90, reason="r", hook="A strong line", title="One two",
                       description="A summary.", hashtags=["#a"], posts=Posts(**dict.fromkeys(
                           ["tiktok", "instagram", "youtube", "linkedin", "facebook", "x"], "copy")))


class ClipProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()
        if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
            raise unittest.SkipTest("ffmpeg not on PATH")

    def test_create_validates_the_source(self):
        with self.assertRaises(UserError):
            projects.create({"kind": "clip", "source": "not a url"})
        p = projects.create({"kind": "clip", "source": "https://example.com/watch?v=abc"})
        self.assertEqual(p["name"], "watch?v=abc")
        self.assertEqual(p["brief"]["orientation"], "9:16")

    def test_full_clip_job_export_and_reclip(self):
        src = config.MEDIA_DIR / "fixtures" / "clip-src.mp4"
        src.parent.mkdir(parents=True, exist_ok=True)
        make_talking_head(str(src))
        p = projects.create({"kind": "clip", "source": str(src), "n": 1, "min_len": 5, "max_len": 10})
        with mock.patch.object(clips_app.transcribe, "transcribe", lambda v, w: fake_transcript(2.5)), \
             mock.patch.object(clips_app.select, "find_clips", lambda t, n, a, b: [one_clip()]), \
             mock.patch.object(jobs, "emit"):
            job = jobs.start(p["id"], kind="clip")
            for _ in range(1200):
                job = jobs.get(job["id"])
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(0.1)
        self.assertEqual(job["status"], "completed", job["error"])
        rows = clips_app.list_(p["id"])
        self.assertEqual(len(rows), 1)
        clip = rows[0]
        self.assertEqual(clip["status"], "ready")
        self.assertTrue((config.MEDIA_DIR / clip["video_path"]).exists())
        self.assertTrue((config.MEDIA_DIR / clip["cover_path"]).exists())
        self.assertEqual(clip["posts"]["tiktok"], "copy")

        result = export.export_project(p["id"], None)
        self.assertEqual(result["pieces"], 1)
        folder = Path(result["dir"]) / "001_one-two"
        self.assertTrue((folder / "clip.mp4").exists())
        self.assertTrue((folder / "cover.jpg").exists())
        self.assertTrue((folder / "captions.ass").exists())
        meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["posts"]["tiktok"], "copy")
        self.assertEqual(clips_app.list_(p["id"])[0]["status"], "exported")
        shutil.rmtree(result["dir"])  # other tests scan the shared exports/<date> tree: leave it as we found it
        with database.connect() as conn:
            conn.execute("DELETE FROM exports WHERE project_id = ?", (p["id"],))

        # re-clip replaces the previous take: rows are deleted first, so one fresh take remains
        with mock.patch.object(clips_app.transcribe, "transcribe", lambda v, w: fake_transcript(2.5)), \
             mock.patch.object(clips_app.select, "find_clips", lambda t, n, a, b: [one_clip()]), \
             mock.patch.object(jobs, "emit"):
            job = jobs.start(p["id"], kind="clip")
            for _ in range(1200):
                job = jobs.get(job["id"])
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(0.1)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(clips_app.list_(p["id"])), 1)

    def test_per_minute_clip_count_capped_at_thirty(self):
        from app.clipper import acquire
        src = config.MEDIA_DIR / "fixtures" / "clip-src2.mp4"
        make_talking_head(str(src))
        p = projects.create({"kind": "clip", "source": str(src), "min_len": 5, "max_len": 10})
        _, work = acquire.acquire(str(src), config.MEDIA_DIR / clips_app.WORK)  # local file: no download
        clips_app.save_transcript(work.name, {"language": "en", "words": [],
                                              "segments": [{"start": 0, "end": 3600, "text": "x"}]})
        asked = []
        try:
            with mock.patch.object(clips_app.select, "find_clips", lambda t, n, a, b: asked.append(n) or []), \
                 mock.patch.object(jobs, "emit"):
                job = jobs.start(p["id"], kind="clip")  # n=None -> about one clip per minute, capped at 30
                for _ in range(400):
                    job = jobs.get(job["id"])
                    if job["status"] not in ("queued", "running"):
                        break
                    time.sleep(0.05)
            self.assertEqual(job["status"], "completed")
            self.assertEqual(asked, [30])
            self.assertEqual(clips_app.list_(p["id"]), [])
        finally:
            (config.MEDIA_DIR / clips_app.WORK / work.name / "transcript.json").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
