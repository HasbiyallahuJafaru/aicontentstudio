"""Still designs (app/design.py) and caption styles (app/clipper/captions.py): the typographic rules hold for every
design and every style, at small sizes so the suite stays fast."""
import os
import tempfile
import unittest

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from PIL import Image, ImageStat  # noqa: E402

from app import design  # noqa: E402
from app.clipper.captions import PRESETS, captions  # noqa: E402

PAL = {"text": "#FFFFFF", "overlay": "#18201E", "primary": "#53645F", "dark": "#18201E", "light": "#E5ECE8",
       "secondary": "#A7B4AD"}
QUOTES = [
    {"text": "Life has no script. Live it."},
    {"text": "Your comfort zone will kill you.", "kicker": "Friendly reminder", "emphasis": "kill you"},
    {"text": "The impediment to action advances action. What stands in the way becomes the way.",
     "author": "Marcus Aurelius"},
]


def photo():
    img = Image.new("RGB", (640, 900), "#6B5A48")
    img.paste("#2B2520", (0, 500, 640, 900))
    return img


class Designs(unittest.TestCase):
    def test_every_design_renders_every_quote_with_and_without_a_photo(self):
        for name in design.DESIGNS:
            for q in QUOTES:
                for pic in (photo(), None):
                    with self.subTest(design=name, quote=q["text"][:20], photo=pic is not None):
                        img = design.compose(name, pic, q, PAL, 432, 540)
                        self.assertEqual(img.size, (432, 540))
                        self.assertGreater(ImageStat.Stat(img.convert("L")).stddev[0], 8, "a design, not a flat field")

    def test_text_stays_inside_the_margins(self):
        # type-only render on a flat backdrop: the outer 3% must hold no glyph ink in any design
        for name in design.DESIGNS:
            with self.subTest(design=name):
                img = design.compose(name, None, QUOTES[2], PAL, 432, 540)
                band = round(432 * 0.03)
                for box in ((0, 0, band, 540), (432 - band, 0, 432, 540)):
                    lo, hi = img.convert("L").crop(box).getextrema()
                    self.assertLess(hi - lo, 120, f"{name}: ink in the side margin")

    def test_every_sentence_starts_a_line_when_it_can(self):
        st = design.Style("montserrat", 60, design.INK)
        lines = design.breaks(design.tokens("Your only limit is you. Stop waiting. Start doing."), st, 700, 6)
        firsts = [ln[0][0] for ln in lines]
        self.assertIn("Stop", firsts)
        self.assertIn("Start", firsts)
        for ln in lines:
            self.assertLessEqual(design.line_w(st, ln), 700)

    def test_no_lone_last_word(self):
        st = design.Style("sans", 40, "#FFFFFF")
        lines = design.breaks(design.tokens("Show up before the feeling does and the feeling follows you"), st, 500)
        self.assertGreater(len(lines[-1]), 1)

    def test_pick_honours_the_user_then_the_genre_and_rotates(self):
        self.assertEqual(design.pick("paper", "stoic", None, 0, "x y z"), "paper")
        picks = {design.pick("auto", "stoic", None, i, "Short line here.") for i in range(3)}
        self.assertEqual(picks, set(design.GENRE_DESIGNS["stoic"]))
        long_quote = " ".join(["word"] * 18)
        self.assertNotIn(design.pick("auto", "stoic", None, 1, long_quote), {"statement"}, "statement needs short copy")

    def test_copy_takes_a_short_last_sentence_as_emphasis(self):
        self.assertEqual(design.copy_for({"text": "Life has no script. Live it."})["emphasis"], "Live it.")
        self.assertEqual(design.copy_for({"text": "One line only.", "emphasis": "not in it"})["emphasis"], "")


WORDS = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.38}
         for i, w in enumerate("Your comfort zone will kill you, so move.".split())]


class CaptionStyles(unittest.TestCase):
    def events(self, ass):
        return [ln for ln in ass.splitlines() if ln.startswith("Dialogue")]

    def test_every_style_writes_events_in_its_own_face(self):
        for key, p in PRESETS.items():
            with self.subTest(style=key):
                ass = captions(WORDS, 0, 5, style={"style": key})
                self.assertTrue(self.events(ass))
                family = design.font(p["font"], 40).getname()[0]
                self.assertIn(f"Style: Caption,{family},", ass)

    def test_plain_styles_never_colour_key_words(self):
        ass = captions(WORDS, 0, 5, emphasis=["kill"], style={"style": "clean"})
        self.assertNotIn("\\c&H", ass)
        self.assertIn("\\fad(", ass)

    def test_pop_shows_one_word_and_short_words_ride_along(self):
        texts = [e.split(",,", 1)[1] for e in self.events(captions(WORDS, 0, 5, style={"style": "pop"}))]
        plain = [t.split("}")[-1] for t in texts]
        self.assertIn("WILL", plain, "a 4-letter word stands alone")
        self.assertIn("SO MOVE.", plain, "a short word waits for the next")

    def test_position_size_case_font_and_colour_choices(self):
        ass = captions(WORDS, 0, 5, emphasis=["kill"], style={"style": "karaoke", "position": "upper", "size": "large",
                                                             "case": "upper", "font": "poster", "highlight": "green"})
        style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style:"))
        fields = style_line.split(",")
        self.assertEqual(fields[1], "Big Shoulders")
        self.assertEqual(fields[2], str(round(88 * 1.2)))
        self.assertEqual(fields[18], "8", "upper = top-centre alignment")
        self.assertIn("YOUR", ass)
        self.assertIn("&H007AE08E&", ass, "green highlight, BGR")

    def test_palette_highlight_uses_the_project_accent(self):
        ass = captions(WORDS, 0, 5, emphasis=["kill"], style={"style": "serif"}, accent="#C08040")
        self.assertIn("&H004080C0&", ass)


if __name__ == "__main__":
    unittest.main()
