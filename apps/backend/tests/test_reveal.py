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
        self.assertTrue(text.startswith("Marcus Aurelius once wrote..."))
        self.assertEqual([p["kind"] for p in parts], ["intro", "quote", "quote", "source", "lesson"])
        self.assertIn("\n\nMeditations.\n\n", text)
        self.assertEqual(parts[-1]["words"][1], len(text.split()))  # word ranges cover the spoken text exactly
        said, _ = reveal.script({"text": QUOTE["text"], "author": "Seneca"})
        self.assertTrue(said.startswith("Seneca once said..."))  # no book named: "said", and nothing after
        bare, parts = reveal.script({"text": QUOTE["text"], "author": None})
        self.assertEqual(bare, QUOTE["text"])
        self.assertEqual({p["kind"] for p in parts}, {"quote"})

    def test_chunks_are_two_or_three_words(self):
        words = "the impediment to action advances action what stands in the way becomes the way".split()
        sizes = [len(g) for g in reveal.chunks(words)]
        self.assertTrue(all(2 <= s <= 4 for s in sizes), sizes)
        self.assertEqual(sum(sizes), len(words))
        self.assertEqual(reveal.chunks(["over", "your", "mind,", "not", "outside"]), [[0, 1, 2], [3, 4]])

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
        self.assertGreater(after - before, 2.0)  # two sections, each given ~1.5 s it didn't have
        for k in quote_ends:
            if k < len(out):
                self.assertGreaterEqual(out[k][0] - out[k - 1][1], reveal.HOLD - 0.01)
        sub, post_at = reveal.ass(parts, out, 540, 960)
        events = []
        for line in sub.splitlines():
            if line.startswith("Dialogue:"):
                f = line.split(",", 9)
                events.append((sum(float(x) * m for x, m in zip(f[1].split(":"), (3600, 60, 1))),
                               sum(float(x) * m for x, m in zip(f[2].split(":"), (3600, 60, 1)))))
        for (a0, a1), (b0, _) in zip(events, events[1:]):
            self.assertLessEqual(a1, b0 + 0.01, sub)  # one line on screen at a time
        self.assertGreaterEqual(post_at, events[-1][1] - 0.01)


if __name__ == "__main__":
    unittest.main()
