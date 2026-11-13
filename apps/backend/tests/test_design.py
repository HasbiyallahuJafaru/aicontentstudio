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
    {"text": "Your comfort zone will kill you."},
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

    def test_beat_stresses_the_punchline_word(self):
        toks = design.beat(design.tokens("You have power over your mind. Realize this, and you will find strength."))
        self.assertEqual([w for w, e in toks if e], ["strength."])
        self.assertEqual(sum(e for _, e in design.beat(design.tokens("It is what it is."))), 1)  # all stopwords: still one

    def test_a_retired_design_name_still_renders(self):
        img = design.compose("noir", None, {"text": "Short line here."}, {"primary": "#8A5A2B", "dark": "#111111"},
                             216, 270)
        self.assertEqual(img.size, (216, 270))

    def test_pick_honours_the_user_then_the_genre_and_rotates(self):
        self.assertEqual(design.pick("verse", "stoic", None, 0, "x y z"), "verse")
        picks = {design.pick("auto", "stoic", None, i, "Short line here.")
                 for i in range(len(design.GENRE_DESIGNS["stoic"]))}  # a full rotation uses every design the genre has
        self.assertEqual(picks, set(design.GENRE_DESIGNS["stoic"]))
        long_quote = " ".join(["word"] * 36)
        self.assertNotIn(design.pick("auto", "stoic", None, 3, long_quote), {"giant", "moon"}, "short-copy designs")
        for name in design.DESIGNS:  # every design renders, with and without a photo
            self.assertEqual(design.compose(name, None, {"text": "Short line here."}, {"primary": "#8A5A2B",
                             "dark": "#1E1611", "light": "#F1ECE4"}, 216, 270).size, (216, 270))

    def test_copy_is_just_the_quote_and_author(self):  # owner 2026-11-08: no emphasis, no kicker
        old = {"text": "Life has  no script.", "author": " Seneca ", "emphasis": "script", "kicker": "Note"}
        self.assertEqual(design.copy_for(old), {"text": "Life has no script.", "author": "Seneca"})


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
                family, style = design.font(p["font"], 40).getname()
                if style not in ("Regular", "Bold", "Italic", "Bold Italic"):  # "Montserrat" alone falls back to Arial
                    family = f"{family} {style}"
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

    def test_marker_block_sits_under_the_spoken_word_and_glides(self):
        evs = self.events(captions(WORDS, 0, 5, style={"style": "marker"}, accent="#E0A030"))
        blocks = [e for e in evs if "\\p1" in e]
        texts = [e for e in evs if e.startswith("Dialogue: 1,")]
        self.assertEqual(len(blocks), len(texts), "one block per spoken word")
        self.assertIn("\\move(", blocks[1], "the block slides to the next word")
        self.assertIn("&H0030A0E0&", blocks[0], "palette colour, BGR")
        for e in evs:  # every phrase stays inside the side margins (the right-hand button column included)
            pos = e.split("\\pos(")[1] if "\\pos(" in e else e.split("\\move(")[1]
            self.assertTrue(0 < float(pos.split(",")[0]) < 1080 - 160)

    def test_duet_sets_the_beat_word_in_the_italic_serif(self):
        evs = self.events(captions([{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3}
                                    for i, w in enumerate("And you will find strength.".split())], 0, 3,
                                   style={"style": "duet"}))
        last = evs[-1]
        self.assertIn("\\fnInstrument Serif\\i1", last)
        self.assertTrue(last.split("\\i1")[1].split("}", 1)[1].startswith("strength."))
        self.assertIn("\\alpha&HFF&", evs[0], "unspoken words hold their place, unseen")


if __name__ == "__main__":
    unittest.main()
