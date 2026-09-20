"""Two-pass DeepSeek selection: pass 1 scans the whole transcript for candidate moments, pass 2 reads those
candidates with a little surrounding context, drops the ones that don't stand alone, picks the best diverse set
and writes hooks, titles and per-platform posts. Timestamps always stay property of pass 1."""
import logging
import math

from pydantic import BaseModel, model_validator

from app import config, settings
from app.creative.model import DeepSeekModel
from app.errors import UserError

log = logging.getLogger("clipper.select")

PASS1 = """You scan a video transcript for moments that could become standalone short-form clips.
A good clip makes sense on its own: strong opening, one complete thought, clear payoff.
Prefer insight, story, strong opinion, surprise, humor and practical advice over mere loudness.
The first 1-2 seconds decide retention: a moment must open on a strong first line (a claim, question or
story jump), never mid-sentence filler like "so", "and", "anyway" or a back-reference like "like I said".
Each moment is {min:g}-{max:g} seconds, starts at a segment start, ends at a segment end, and does not overlap others.
Return json only, up to {n} moments:
{{"moments": [{{"start": 734.2, "end": 781.6, "score": 80, "reason": "why it works"}}]}}"""

PASS2 = """You are a senior short-form video editor. From the numbered candidate clips, pick the best {n} and write their copy.
Each candidate shows a little transcript before and after: use it to judge, never to include.
Drop any candidate that would not stand alone: one that opens mid-thought or on filler/back-reference ("so",
"anyway", "like I said"), leans on what comes before or after to make sense, or ends before its payoff lands.
Prefer clips whose first sentence is a hook strong enough to stop a scroll, and pick a diverse set: skip a
candidate that makes the same point as one you already picked.
You may trim a clip's edges to the nearest complete sentence by giving a tighter "start"/"end" (seconds,
within the candidate's own bounds); omit them to keep the candidate as-is.
Use only what is actually said in each clip. Write natively per platform: TikTok and Instagram casual with a few hashtags,
YouTube Shorts a searchable description, LinkedIn a professional takeaway, Facebook conversational.
Never exceed these lengths in characters: {limits}.
Return json only, best clip first:
{{"clips": [{{"id": 3, "score": 94, "hook": "on-screen opening line, max 8 words", "title": "short title",
"description": "1-2 sentence summary", "hashtags": ["#example"],
"posts": {{"tiktok": "...", "instagram": "...", "youtube": "...", "linkedin": "...", "facebook": "...", "x": "..."}}}}]}}"""

# Longest post each network takes, in characters (checked 2026-09-18). Conservative where a network's cap depends
# on the surface: we post reels, and a reel's caption is shorter than a page post's.
LIMITS = {"tiktok": 2200, "instagram": 2200, "youtube": 5000, "linkedin": 3000, "facebook": 2200, "x": 280}


class Moment(BaseModel):
    start: float
    end: float
    score: int
    reason: str


class Moments(BaseModel):
    moments: list[Moment]


def fits(text: str, limit: int) -> str:
    """Trim to `limit` on a word boundary. The copywriter is told the caps; this is the net under it, because one
    over-long post must not fail a whole video's job."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-—") or text[:limit]


class Posts(BaseModel):
    tiktok: str
    instagram: str
    youtube: str
    linkedin: str
    facebook: str
    x: str

    @model_validator(mode="after")
    def trim(self):
        for network, limit in LIMITS.items():
            setattr(self, network, fits(getattr(self, network), limit))
        return self


class Pick(BaseModel):
    id: int
    score: int
    hook: str
    title: str
    description: str
    hashtags: list[str]
    posts: Posts
    start: float | None = None  # optional trim: must sit inside the candidate
    end: float | None = None


class Picks(BaseModel):
    clips: list[Pick]


class Clip(BaseModel):
    start: float
    end: float
    score: int
    reason: str
    hook: str
    title: str
    description: str
    hashtags: list[str]
    posts: Posts


def _ask(system: str, user: str, parse) -> object:
    """Call the model in JSON mode, up to 3 tries; `parse` validates (raises ValueError on bad output)."""
    key = config.SECRETS.get("DEEPSEEK_API_KEY")
    if not key:
        raise UserError("Add your DeepSeek API key in Settings to clip videos.")
    deepseek = DeepSeekModel(key, settings.get()["ai_model"], 1.0, 64000)  # 30 clips of copy ~12K tokens plus thinking
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(1, 4):
        text = deepseek._chat(messages)
        try:
            return parse(text)
        except ValueError as e:  # pydantic's ValidationError is a ValueError
            log.warning("rejected model output (attempt %d): %s", attempt, e)
    raise UserError("DeepSeek kept returning unusable clip selections. Try again in a few minutes.")


def parse_moments(content: str, duration: float, min_len: float, max_len: float) -> list[Moment]:
    """Never trust model output: drop moments outside the video or off the length range; on overlap keep the
    higher score. Returns chronological order."""
    kept = []
    for m in sorted(Moments.model_validate_json(content).moments, key=lambda m: -m.score):
        if (0 <= m.start < m.end <= duration + 1 and min_len * 0.8 <= m.end - m.start <= max_len * 1.2
                and all(m.end <= k.start or m.start >= k.end for k in kept)):
            kept.append(m)
    if not kept:
        raise ValueError("no usable moments")
    return sorted(kept, key=lambda m: m.start)


def parse_picks(content: str, moments: list[Moment], n: int, min_len: float = 0,
                max_len: float = math.inf) -> list[Clip]:
    """Timestamps always come from pass 1; pass 2 may only choose candidate ids, optionally trim a clip inside
    its own bounds (trims outside the length range are ignored), and write copy."""
    clips, used = [], set()
    for p in Picks.model_validate_json(content).clips:
        if 0 <= p.id < len(moments) and p.id not in used:
            used.add(p.id)
            m = moments[p.id]
            start, end = m.start, m.end
            if p.start is not None and p.end is not None and m.start <= p.start < p.end <= m.end \
                    and min_len * 0.8 <= p.end - p.start <= max_len * 1.2:
                start, end = p.start, p.end
            clips.append(Clip(start=start, end=end, reason=m.reason, **p.model_dump(exclude={"id", "start", "end"})))
    if not clips:
        raise ValueError("no valid candidate ids")
    return clips[:n]


def find_clips(transcript: dict, n: int, min_len: float, max_len: float) -> list[Clip]:
    segments, words = transcript["segments"], transcript["words"]
    lines = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)
    moments = _ask(PASS1.format(min=min_len, max=max_len, n=min(3 * n, 90)), lines,
                   lambda c: parse_moments(c, segments[-1]["end"], min_len, max_len))
    said = lambda a, b: " ".join(w["word"] for w in words if a <= w["start"] < b)
    candidates = "\n\n".join(
        f"#{i} ({m.end - m.start:.0f}s) {m.reason}\n"
        f"before: {said(m.start - 15, m.start) or '(silence)'}\n"
        f"{said(m.start, m.end)}\n"
        f"after: {said(m.end, m.end + 15) or '(silence)'}"
        for i, m in enumerate(moments))
    limits = ", ".join(f"{network} {cap}" for network, cap in LIMITS.items())
    return _ask(PASS2.format(n=n, limits=limits), candidates,
                lambda c: parse_picks(c, moments, n, min_len, max_len))


def snap(start: float, end: float, words: list[dict]) -> tuple[float, float]:
    """Move cut points to sentence boundaries where one sits within 1.5s, else to whole words: never start a
    clip mid-sentence or end it between sentences."""
    sentence_starts = [w["start"] for a, w in zip(words, words[1:]) if a["word"][-1:] in ".?!"]
    sentence_ends = [w["end"] for w in words if w["word"][-1:] in ".?!"]
    near = lambda t, edges: min((e for e in edges if abs(e - t) <= 1.5), key=lambda e: abs(e - t), default=None)
    s, e = near(start, sentence_starts), near(end, sentence_ends)
    start = s if s is not None else max((w["start"] for w in words if w["start"] <= start + 0.2), default=start)
    end = e if e is not None else min((w["end"] for w in words if w["end"] >= end - 0.2), default=end)
    return start, end
