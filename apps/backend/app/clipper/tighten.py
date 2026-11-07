"""Tightening: turn a clip into the source ranges it keeps. Dead air and filler words are cut out, and an
optional cold open (the clip's strongest line) plays first. The render joins the ranges; captions are retimed
onto the joined timeline with `retime`."""
import re

MAX_GAP = 0.35  # a pause longer than this is cut down to PAD of breath on each side
PAD = 0.12
# ponytail: only unambiguous fillers. "like"/"you know" need context; Whisper also drops most fillers itself.
FILLERS = {"um", "uh", "uhm", "umm", "uhh", "er", "erm", "ah", "hmm", "mm", "mhm"}


def bare(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def keep(words: list[dict], start: float, end: float) -> list[tuple[float, float]]:
    """Source ranges inside [start, end] that keep every real word and drop pauses over MAX_GAP."""
    spoken = [w for w in words if start <= w["start"] < end and bare(w["word"]) not in FILLERS]
    if not spoken:
        return [(start, end)]
    ranges, a = [], start
    for prev, w in zip(spoken, spoken[1:]):
        if w["start"] - prev["end"] > MAX_GAP:
            ranges.append((a, prev["end"] + PAD))
            a = w["start"] - PAD
    ranges.append((a, end))
    # the clip's own edges can sit inside a long lead-in/tail pause: trim those too
    first, last = spoken[0]["start"] - PAD, min(spoken[-1]["end"] + PAD, end)
    ranges[0] = (max(ranges[0][0], first), ranges[0][1])
    ranges[-1] = (ranges[-1][0], min(ranges[-1][1], max(last, ranges[-1][0] + 0.05)))
    return [(round(a, 3), round(b, 3)) for a, b in ranges if b - a > 0.05]


def plan(words: list[dict], start: float, end: float,
         cold_open: tuple[float, float] | None = None) -> list[tuple[float, float]]:
    """The full edit: the cold open's ranges (when there is one, given at word edges: padded so its first and
    last sounds are not clipped), then the clip's."""
    teaser = keep(words, cold_open[0] - PAD, cold_open[1] + PAD) if cold_open else []
    return teaser + keep(words, start, end)


def retime(words: list[dict], ranges: list[tuple[float, float]]) -> list[dict]:
    """Words placed on the joined timeline: each range starts where the previous one ended."""
    out, offset = [], 0.0
    for a, b in ranges:
        out += [w | {"start": round(offset + w["start"] - a, 3), "end": round(offset + min(w["end"], b) - a, 3)}
                for w in words if a <= w["start"] < b]
        offset += b - a
    return out


def to_words(words: list[dict], start: float, end: float) -> tuple[float, float]:
    """Snap a model-given span to the words it covers (start of the first, end of the last)."""
    inside = [w for w in words if w["end"] > start and w["start"] < end]
    return (inside[0]["start"], inside[-1]["end"]) if inside else (start, end)
