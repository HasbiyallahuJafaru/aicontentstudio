"""Motion graphics: template data, compositing graph, schema, and one real HyperFrames render through a browser."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app import config, database, motion  # noqa: E402
from app.clipper.render_clip import render  # noqa: E402
from app.creative.schemas import PieceContent  # noqa: E402

from tests.test_clipper_port import make_talking_head  # noqa: E402


class HookWords(unittest.TestCase):
    def test_starred_words_are_keywords_across_phrases_and_punctuation(self):
        self.assertEqual(motion.hook_words("Most people quit *one day* early."),
                         [{"t": "Most", "key": False}, {"t": "people", "key": False}, {"t": "quit", "key": False},
                          {"t": "one", "key": True}, {"t": "day", "key": True}, {"t": "early.", "key": False}])
        self.assertEqual(motion.hook_words("Stop *waiting*, start.")[1], {"t": "waiting,", "key": True})
        self.assertEqual(len(motion.hook_words("a " * 20)), motion.MAX_HOOK_WORDS)

    def test_anchor_time_matches_the_spoken_word(self):
        words = [{"word": "At", "start": 0.0}, {"word": "3AM,", "start": 0.4}, {"word": "nobody", "start": 0.9}]
        self.assertEqual(motion.anchor_time(words, "3am"), 0.4)
        self.assertIsNone(motion.anchor_time(words, "noon"))


class Compositing(unittest.TestCase):
    def test_overlay_graph_shifts_each_layer_and_decodes_alpha(self):
        args, chain, out = motion.overlay_graph("v", [{"path": Path("h.webm"), "start": 0.0},
                                                      {"path": Path("c.webm"), "start": 4.5}], 3)
        self.assertEqual(args, ["-c:v", "libvpx-vp9", "-i", "h.webm", "-c:v", "libvpx-vp9", "-i", "c.webm"])
        self.assertEqual(chain[2], "[4:v]setpts=PTS+4.500/TB[ml1]")
        self.assertEqual(chain[3], "[mo0][ml1]overlay=0:0:eof_action=pass:format=auto[mo1]")
        self.assertEqual(out, "mo1")
        self.assertEqual(motion.overlay_graph("v", [], 1), ([], [], "v"), "no layers: the stream passes through")

    def test_off_means_no_layers_and_no_browser(self):
        with mock.patch.object(motion, "_render", side_effect=AssertionError("must not render")):
            self.assertEqual(motion.layers("hope", 1080, 1920, hook="Anything"), [])  # suite runs with ACS_NO_MOTION
        with mock.patch.dict(os.environ, {"ACS_NO_MOTION": ""}), mock.patch.object(motion, "browser", lambda: None):
            self.assertFalse(motion.enabled(), "no Edge/Chrome: plain edit")


class Schema(unittest.TestCase):
    def test_pieces_without_motion_fields_still_load_and_callouts_cap_at_two(self):
        base = {"quote": {"text": "Keep going anyway."}, "narration": {"text": "x" * 30, "delivery": "calm"},
                "visual": {"preferred_type": "video", "search_query": "abc", "secondary_query": "abc", "mood": "calm"},
                "design": {"text_density": "low", "animation": "slow", "composition": "editorial"},
                "metadata": {"title": "abc", "description": "d" * 12, "caption": "c" * 12, "hashtags": ["#a", "#b", "#c"],
                             "keywords": ["a", "b", "c"], "alt_text": "a" * 12}}
        self.assertEqual(PieceContent.model_validate(base).hook, "")
        many = [{"text": f"{i} AM", "word": "am"} for i in range(5)]
        self.assertEqual(len(PieceContent.model_validate(base | {"callouts": many}).callouts), 2)


@unittest.skipUnless(motion.browser() and motion._runner(), "needs Edge/Chrome and the HyperFrames runner")
class RealRender(unittest.TestCase):
    """The template's script must actually run: a JS error renders a fully transparent layer, silently."""

    def test_hook_layer_has_visible_text_and_composites_into_a_clip(self):
        database.migrate()
        with mock.patch.dict(os.environ, {"ACS_NO_MOTION": ""}):
            layers = motion.layers("clip", 360, 640, hook="Most people quit *one day* early")
        self.assertEqual(len(layers), 1)
        alpha = subprocess.run([config.FFMPEG, "-v", "error", "-c:v", "libvpx-vp9", "-ss", "1.2", "-i",
                                str(layers[0]["path"]), "-frames:v", "1", "-vf", "alphaextract", "-f", "rawvideo",
                                "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
        self.assertGreater(sum(b > 200 for b in alpha), 2000, "the hook's words must be opaque mid-animation")
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "talk.mp4", Path(tmp) / "clip.mp4"
            make_talking_head(str(src), 4)
            render(src, 0, 4, out, [], burn=False, orientation="9:16", layers=layers)
            probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                               "-of", "json", str(out)], check=True, capture_output=True).stdout)
            self.assertAlmostEqual(float(probe["format"]["duration"]), 4.0, delta=0.2)
            frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.2", "-i", str(out), "-frames:v", "1",
                                    "-f", "rawvideo", "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
            self.assertGreater(len(set(frame)), 3, "the plain gray clip now carries the title")
