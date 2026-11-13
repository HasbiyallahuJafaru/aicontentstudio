"""The voiced quote video's word reveal (reveal.py, owner 2026-11-12)."""
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from app import reveal

QUOTE = {"text": "You have power over your mind, not outside events. Realize this, and you will find strength.",
         "author": "Marcus Aurelius", "source": "Meditations"}


def speech_wav(path: Path, spans: list[tuple[float, float]], seconds: float, rate: int = 8000) -> None:
    """Loud where someone is 'speaking', silent elsewhere."""
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        frames += struct.pack("<h", (8000 if i % 2 else -8000) if any(a <= t < b for a, b in spans) else 0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


class Reveal(unittest.TestCase):
    def test_script_opens_with_the_author_and_ends_with_book_and_lesson(self):
        text, parts = reveal.script(QUOTE, "The word that matters is power.")
        self.assertTrue(text.startswith("Marcus Aurelius once wrote:"))
        self.assertEqual([p["kind"] for p in parts], ["intro", "quote", "quote", "source", "lesson"])
        self.assertIn("\n\nMeditations.\n\n", text)
        self.assertEqual(parts[-1]["words"][1], len(text.split()))  # word ranges cover the spoken text exactly
        said, _ = reveal.script({"text": QUOTE["text"], "author": "Seneca"})
        self.assertTrue(said.startswith("Seneca once said:"))  # no book named: "said", and nothing after
        bare, parts = reveal.script({"text": QUOTE["text"], "author": None})
        self.assertEqual(bare, QUOTE["text"])
        self.assertEqual({p["kind"] for p in parts}, {"quote"})

    def test_long_sentences_split_at_commas(self):
        long = ("If you are distressed by anything external, the pain is not due to the thing itself, but to your "
                "estimate of it, and this you have the power to revoke at any moment.")
        self.assertTrue(all(len(s.split()) <= reveal.SECTION_MAX for s in reveal.sections(long)))
        self.assertEqual(" ".join(reveal.sections(long)), long)

    def test_timeline_fills_words_the_transcript_misheard(self):
        text = "Marcus Aurelius once wrote"
        heard = [{"word": "Marcos", "start": 0.0, "end": 0.4}, {"word": "Aurelius", "start": 0.4, "end": 0.9},
                 {"word": "once", "start": 1.0, "end": 1.2}, {"word": "wrote:", "start": 1.2, "end": 1.6}]
        times = reveal.timeline(text, heard, 2.0)
        self.assertEqual(times[1], (0.4, 0.9))
        self.assertEqual(times[3], (1.2, 1.6))
        self.assertLessEqual(times[0][1], times[1][0])  # the unmatched name lands before the next word

    def test_stretch_gives_each_section_a_pause_and_the_reveal_never_overlaps(self):
        text, parts = reveal.script(QUOTE)
        tokens = text.split()
        # one word every 0.3 s with no pause anywhere, and a transcript that runs each word's end into the next
        times = [(i * 0.3, (i + 1) * 0.3) for i in range(len(tokens))]
        spans = [(a, a + 0.22) for a, _ in times]
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "n.wav"
            speech_wav(wav, spans, len(tokens) * 0.3 + 0.5)
            with wave.open(str(wav)) as w:
                before = w.getnframes() / w.getframerate()
            out = reveal.stretch(wav, parts, times)
            with wave.open(str(wav)) as w:
                after = w.getnframes() / w.getframerate()
        quote_ends = [p["words"][1] for p in parts if p["kind"] == "quote"]
        self.assertGreater(after - before, 1.0)  # two sentences, each given a breath it didn't have
        for k in quote_ends:
            if k < len(out):
                self.assertGreaterEqual(out[k][0] - out[k - 1][1], reveal.HOLD - 0.01)
        sub = reveal.ass(parts, out, 540, 960, until=out[-1][1] + 5)
        events = [ln for ln in sub.splitlines() if ln.startswith("Dialogue:")]

        def secs(stamp):
            return sum(float(x) * m for x, m in zip(stamp.split(":"), (3600, 60, 1)))
        spans = [(secs(e.split(",")[1]), secs(e.split(",")[2])) for e in events]
        for (a0, a1), (b0, _) in zip(spans, spans[1:]):
            self.assertAlmostEqual(a1, b0, places=1)  # each state hands straight to the next: no flicker, no overlap
        self.assertAlmostEqual(spans[-1][1], out[-1][1] + 5, places=1)  # the finished quote holds to the end
        shown = [p for p in parts if p["kind"] in ("intro", "quote")]
        self.assertEqual(len(events), sum(len(p["text"].split()) for p in shown) + 1)  # a word per event + the book
        last = events[-1]
        self.assertNotIn("alpha&HFF&}", last.split("[")[0])  # every quote word fully on; only the book fades in
        self.assertIn("[Meditations]", last)
        self.assertIn("Instrument Sans", sub)  # the plain in-app sans, never the bold caption face

    def test_only_spoken_words_are_visible(self):
        text, parts = reveal.script(QUOTE)
        times = [(i * 0.5, i * 0.5 + 0.4) for i in range(len(text.split()))]
        events = [ln for ln in reveal.ass(parts, times, 540, 960, 30.0).splitlines() if ln.startswith("Dialogue:")]
        third = events[2]  # "Marcus Aurelius once": two words on, "once" fading in, the rest hidden but laid out
        self.assertEqual(third.count("alpha&H00&}"), 2)
        self.assertIn(r"alpha&HFF&\t(0,180,\alpha&H00&)}once", third)
        self.assertIn("alpha&HFF&}strength.", third)  # already in place, invisible: the layout never moves

    def test_finished_is_when_the_book_lands(self):
        text, parts = reveal.script(QUOTE, "A lesson.")
        times = [(i * 0.5, i * 0.5 + 0.4) for i in range(len(text.split()))]
        book = next(p for p in parts if p["kind"] == "source")["words"][0]
        self.assertEqual(reveal.finished(parts, times), times[book][0])  # never waits for the lesson

if __name__ == "__main__":
    unittest.main()
