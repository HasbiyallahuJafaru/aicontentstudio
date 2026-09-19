"""Milestone 4: deterministic analysis, quality, palette engine and theme extraction. Pure Pillow, no network."""
import colorsys
import os
import tempfile
import unittest

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app import visual  # noqa: E402

from tests.test_assets import DARK, INVERTED, SOLID, STRIPES, bmp  # noqa: E402

W, B = (255, 255, 255), (0, 0, 0)


class Analyze(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(visual.analyze(bmp(STRIPES)), visual.analyze(bmp(STRIPES)))

    def test_solid_midgray_is_flat_and_centered(self):
        a = visual.analyze(bmp(SOLID))
        self.assertAlmostEqual(a["brightness"], 0.502, delta=0.05)
        self.assertAlmostEqual(a["saturation"], 0, delta=0.01)
        self.assertLess(a["contrast"], 0.05)
        self.assertLess(a["visual_complexity"], 0.02)
        self.assertEqual(a["temperature"], "neutral")
        self.assertEqual(a["subject_position"], "center")
        self.assertEqual(len(a["dominant_colors"]), 1)

    def test_black_and_white_extremes(self):
        self.assertLess(visual.analyze(bmp([B] * 8))["brightness"], 0.02)
        self.assertGreater(visual.analyze(bmp([W] * 8))["brightness"], 0.98)

    def test_temperature(self):
        self.assertEqual(visual.analyze(bmp([(180, 60, 40)] * 8))["temperature"], "warm")
        self.assertEqual(visual.analyze(bmp([(40, 60, 180)] * 8))["temperature"], "cool")

    def test_subject_position_follows_detail(self):
        rest = [(100, 100, 100)] * 5
        left = visual.analyze(bmp([B, W, B] + rest))
        right = visual.analyze(bmp(rest + [B, W, B]))
        self.assertEqual(left["subject_position"], "left")
        self.assertEqual(right["subject_position"], "right")

    def test_symmetric_detail_stays_centered(self):
        self.assertEqual(visual.analyze(bmp(INVERTED))["subject_position"], "center")

    def test_dominant_colors_extracted_as_hex(self):
        a = visual.analyze(bmp(STRIPES))
        self.assertEqual(sorted(a["dominant_colors"]), ["#282828", "#C8C8C8"])


class Quality(unittest.TestCase):
    def test_healthy_stripes_score_high(self):
        self.assertGreater(visual.quality(visual.analyze(bmp(STRIPES))), 0.8)

    def test_near_black_fails_the_floor(self):
        self.assertLess(visual.quality(visual.analyze(bmp(DARK))), visual.QUALITY_FLOOR)

    def test_neon_saturation_penalised(self):
        a = visual.analyze(bmp([(255, 0, 120)] * 8))
        self.assertEqual(visual.no_neon(a["saturation"]), 0.0)


class Palette(unittest.TestCase):
    def test_complete_deterministic_hex(self):
        p = visual.palette(["#253832", "#718078", "#D3DAD6"])
        self.assertEqual(set(p), {"primary", "secondary", "dark", "light", "text", "overlay"})
        self.assertEqual(p, visual.palette(["#253832", "#718078", "#D3DAD6"]))
        for v in p.values():
            self.assertEqual(len(v), 7)
            int(v[1:], 16)

    def test_neon_primary_is_clamped(self):
        p = visual.palette(["#FF0080"])
        _, lightness, sat = colorsys.rgb_to_hls(*visual._rgb(p["primary"]))
        self.assertLessEqual(sat, 0.5)
        self.assertTrue(0.27 <= lightness <= 0.61)

    def test_text_contrasts_with_primary(self):
        self.assertEqual(visual.palette(["#18201E"])["text"], "#FFFFFF")
        self.assertNotEqual(visual.palette(["#D4C46A"])["text"], "#FFFFFF")  # light primary wants dark text

    def test_empty_input_still_yields_tokens(self):
        self.assertEqual(len(visual.palette([])), 6)


class Themes(unittest.TestCase):
    def test_content_words_only(self):
        self.assertEqual(visual.themes_from_query("runner on a mountain ridge at dawn"),
                         ["runner", "mountain", "ridge"])

    def test_deduped_and_capped(self):
        self.assertEqual(visual.themes_from_query("city night city lights skyline"), ["city", "night", "lights"])


if __name__ == "__main__":
    unittest.main()
