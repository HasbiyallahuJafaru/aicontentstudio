"""Prompts for the creative director. Provider-neutral chat messages; every reply must be a JSON object."""
import json

SYSTEM = """You are the creative director of a premium social media studio that makes short cinematic videos and \
editorial images built around one original line of text.

Writing rules:
- Write original lines only. Never quote or imitate a real person, never attribute a line to anyone. "author" is always null.
- Sound like a thoughtful human, not an AI: plain words, no clichés ("unlock", "journey", "embrace", "elevate", \
"in a world where"), no rhetorical questions stacked together, no exclamation marks, at most one comma-heavy sentence.
- The visual quote is short (ideally 5 to 16 words) and must stand alone on screen.
- The narration is the spoken version: 2 to 5 short sentences, 8 to 25 seconds aloud, natural rhythm, not the quote \
copied verbatim (it may end on the quote or a variation).
- Never produce variations of the same sentence across pieces. Vary structure, opening word, rhythm and intensity.
- Visual search queries are concrete, filmable stock-footage searches (subject + setting + light), 3 to 7 words, no \
brand names, no text-in-image requests.
- You never decide colors, font sizes, pixel positions, bitrates or crops.
Reply with a single JSON object and nothing else."""

PLAN_SHAPE = {
    "batch_theme": "string",
    "pieces": [{"angle": "distinct sub-idea of the theme", "visual_subject": "distinct filmable subject",
                "visual_type": "video|image", "intensity": "low|medium|high",
                "narration_style": "e.g. calm reflective, quiet urgent, warm conversational"}],
}

PIECE_SHAPE = {
    "quote": {"text": "string", "author": None},
    "narration": {"text": "string", "delivery": "e.g. calm_reflective"},
    "visual": {"preferred_type": "video|image", "search_query": "string", "secondary_query": "string", "mood": "string"},
    "design": {"text_density": "low|medium|high", "animation": "still|slow|medium",
               "composition": "editorial|centered|minimal|bold"},
    "metadata": {"title": "short title, no hashtags", "description": "2-3 sentences", "caption": "social caption, 1-3 short lines",
                 "hashtags": ["#tag", "5-10 relevant tags"], "keywords": ["5-10 search keywords"],
                 "alt_text": "describes the visual for screen readers"},
}


def _brief(b: dict) -> str:
    parts = [f"Topic: {b['topic']}", f"Tone: {b['tone']}"]
    if b.get("mood"):
        parts.append(f"Mood: {b['mood']}")
    if b.get("audience"):
        parts.append(f"Audience: {b['audience']}")
    fmt = {"automatic": "choose video or image per piece, mostly video", "video": "all video",
           "image": "all image", "video_image": "every piece becomes both a video and an image, so prefer video footage"}
    parts.append(f"Output: {fmt[b['format']]}")
    parts.append("Platforms: " + ", ".join(b["platforms"]))
    return "\n".join(parts)


def _avoid(avoid: list[str]) -> str:
    return ("\n\nRecently used lines. Do not repeat or closely paraphrase any of them:\n" + "\n".join(f"- {a}" for a in avoid)) if avoid else ""


def plan(brief: dict, avoid: list[str]) -> list[dict]:
    n = brief["quantity"]
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""{_brief(brief)}

Plan a batch of exactly {n} piece(s) on this topic. Each piece gets a clearly different angle and a different visual \
subject (no two pieces with the same subject or setting), and the batch varies emotional intensity. They should feel \
like one brand, never like duplicates.{_avoid(avoid)}

Return JSON shaped like: {json.dumps(PLAN_SHAPE)} with exactly {n} item(s) in "pieces"."""},
    ]


def piece(brief: dict, plan, item, avoid: list[str]) -> list[dict]:
    siblings = [p.angle for p in plan.pieces if p.angle != item.angle]
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""{_brief(brief)}

Batch theme: {plan.batch_theme}
This piece: angle "{item.angle}", visual subject "{item.visual_subject}", preferred visual {item.visual_type}, \
intensity {item.intensity}, narration style {item.narration_style}.
Other pieces in the batch cover: {", ".join(siblings) or "none"}. Stay on this piece's angle.{_avoid(avoid)}

Write this piece. Return JSON shaped like: {json.dumps(PIECE_SHAPE)}"""},
    ]


def repair(error: str) -> str:
    return ("That reply did not match the required JSON shape. Validation errors:\n"
            f"{error[:1500]}\n\nReturn the corrected JSON object only, same content, fixed to the shape.")
