"""Tightening: turn a clip into the source ranges it keeps. Long pauses are shortened (not removed: a cut with no
breath "pops") and filler words cut out, and an optional cold open (the clip's strongest line) plays first. The
render joins the ranges; captions are retimed onto the joined timeline with `retime`. Pause and framing values come
from real-edit feedback in appariciojunior/video-editor-skills (vlog-pacing; CC BY-NC, ideas only, no text)."""
import re

MAX_PAUSE = 0.5  # a pause longer than this is shortened to PAUSE_KEEP of air ("tight, loved" for talk content)
PAUSE_KEEP = 0.3  # kept air, split 40% after the last word / 60% before the next so onsets are never clipped
PAD = 0.12  # air kept at the clip's own edges and around the cold open
SILENT_SHARE = 0.85  # a gap is a pause only when this much of it is silent: the rest is a sound Whisper skipped
PUNCH = 1.15  # the cold open is the punch line: pushed in for that line only
JUMP = 1.075  # every other jump cut inside the clip, so a cut reads as a camera change, not a skipped frame
# ponytail: only unambiguous fillers. "like"/"you know" need context; Whisper also drops most fillers itself.
FILLERS = {"um", "uh", "uhm", "umm", "uhh", "er", "erm", "ah", "hmm", "mm", "mhm"}


def bare(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def _quiet(a: float, b: float, quiet: list[tuple[float, float]] | None) -> bool:
    """True when at least SILENT_SHARE of [a, b] sits inside `quiet` (merged silences + fillers). None: no audio
    evidence, trust the word timings."""
    if quiet is None:
        return True
    covered = sum(max(0.0, min(b, y) - max(a, x)) for x, y in quiet)
    return covered >= SILENT_SHARE * (b - a)


def _merge(spans) -> list[tuple[float, float]]:
    out = []
    for x, y in sorted(spans):
        if out and x <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], y))
        else:
            out.append((x, y))
    return out


def keep(words: list[dict], start: float, end: float,
         silences: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """Source ranges inside [start, end] that keep every real word, shorten pauses over MAX_PAUSE to PAUSE_KEEP,
    and drop fillers sitting in them. `silences` (ff.silences) confirms each pause on the waveform: a gap with
    sound in it (a laugh, a word the transcript missed) is kept whole."""
    inside = [w for w in words if start <= w["start"] < end]
    spoken = [w for w in inside if bare(w["word"]) not in FILLERS]
    if not spoken:
        return [(start, end)]
    quiet = None if silences is None else _merge(
        [*silences, *((w["start"], w["end"]) for w in inside if bare(w["word"]) in FILLERS)])
    ranges, a = [], start
    for prev, w in zip(spoken, spoken[1:]):
        if w["start"] - prev["end"] > MAX_PAUSE and _quiet(prev["end"], w["start"], quiet):
            ranges.append((a, prev["end"] + 0.4 * PAUSE_KEEP))
            a = w["start"] - 0.6 * PAUSE_KEEP
    ranges.append((a, end))
    # the clip's own edges can sit inside a long lead-in/tail pause: trim those too
    first, last = spoken[0]["start"] - PAD, min(spoken[-1]["end"] + PAD, end)
    ranges[0] = (max(ranges[0][0], first), ranges[0][1])
    ranges[-1] = (ranges[-1][0], min(ranges[-1][1], max(last, ranges[-1][0] + 0.05)))
    return [(round(a, 3), round(b, 3)) for a, b in ranges if b - a > 0.05]


def plan(words: list[dict], start: float, end: float, cold_open: tuple[float, float] | None = None,
         silences: list[tuple[float, float]] | None = None) -> tuple[list[tuple[float, float]], list[float]]:
    """The full edit: the cold open's ranges (when there is one, given at word edges: padded so its first and
    last sounds are not clipped), then the clip's; and each range's zoom. The teaser is pushed in to PUNCH; the
    clip opens at 100% as a new scene and alternates 100% / JUMP on every jump cut after that."""
    teaser = keep(words, cold_open[0] - PAD, cold_open[1] + PAD, silences) if cold_open else []
    body = keep(words, start, end, silences)
    return teaser + body, [PUNCH] * len(teaser) + [JUMP if i % 2 else 1.0 for i in range(len(body))]


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
