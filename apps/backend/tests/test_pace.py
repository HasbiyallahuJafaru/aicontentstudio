"""Narration pace (owner 2026-11-13: "slower than an average human would speak"): pauses tightened on a curve,
slow reads lifted to a floor, the voice itself untouched."""
import array
import math
import os
import tempfile
import unittest
import wave
from pathlib import Path

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app import tts  # noqa: E402

RATE = 24000


def tone(seconds: float) -> list[int]:
    return [round(8000 * math.sin(2 * math.pi * 180 * i / RATE)) for i in range(round(seconds * RATE))]


def write(path: Path, pieces) -> tts.AudioResult:
    pcm = array.array("h")
    for kind, secs in pieces:
        pcm.extend(tone(secs) if kind == "voice" else [0] * round(secs * RATE))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return tts.AudioResult(path)


def gaps(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as w:
        pcm = array.array("h", w.readframes(w.getnframes()))
    out, run, step = [], 0, RATE // 50
    for i in range(0, len(pcm), step):
        if max(abs(v) for v in pcm[i:i + step]) < 100:
            run += 1
        elif run:
            out.append(run * 0.02)
            run = 0
    return out


class Pace(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_pauses_shrink_but_keep_their_order(self):
        a = write(self.dir / "a.wav", [("voice", 1), ("gap", 0.15), ("voice", 1), ("gap", 0.6), ("voice", 1),
                                       ("gap", 1.2), ("voice", 1)])
        got = gaps(tts.tighten(a).path)
        self.assertEqual(len(got), 3)
        self.assertAlmostEqual(got[0], 0.16, delta=0.05, msg="a breath inside a phrase is untouched")
        self.assertLess(got[1], 0.45)
        self.assertLess(got[2], 0.7, "a 1.2 s pause becomes ~0.6 s")
        self.assertGreater(got[2], got[1], "the long pause stays the longest: the emphasis survives")

    def test_voice_is_never_cut(self):
        a = write(self.dir / "b.wav", [("voice", 1.5), ("gap", 1.0), ("voice", 1.5)])
        before = a.duration
        after = tts.tighten(a).duration
        self.assertAlmostEqual(before - after, (1.0 - tts.PAUSE_MIN) * (1 - tts.PAUSE_KEEP), delta=0.05)

    def test_slow_read_lifted_to_the_floor_fast_read_left_alone(self):
        calls = []
        orig = tts._tempo
        tts._tempo = lambda audio, f: calls.append(f) or audio
        try:
            a = write(self.dir / "c.wav", [("voice", 10)])
            tts.up_to_pace(a, " ".join(["word"] * 30))  # 3 words/s: already at pace
            self.assertEqual(calls, [])
            tts.up_to_pace(a, " ".join(["word"] * 22))  # 2.2 words/s
            self.assertAlmostEqual(calls[-1], tts.PACE_FLOOR / 2.2, places=2)
            tts.up_to_pace(a, " ".join(["word"] * 15))  # 1.5 words/s: capped, never chipmunked
            self.assertEqual(calls[-1], tts.PACE_MAX_LIFT)
            n = len(calls)
            tts.up_to_pace(a, "Keep going.")  # a rate over two words means nothing
            self.assertEqual(len(calls), n)
        finally:
            tts._tempo = orig


if __name__ == "__main__":
    unittest.main()
