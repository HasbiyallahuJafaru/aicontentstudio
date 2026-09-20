"""Prompts for the creative director. Provider-neutral chat messages; every reply must be a JSON object."""
import json

SYSTEM = """You are the creative director of a premium social media studio that makes short cinematic videos and \
editorial images built around one original line of text.

Stay on the brief:
- The line must be recognisably about the given topic. Not ambition, not success, not "growth" in general.
- Write about something specific enough to picture: a moment, an object, an hour of the day, a thing someone does.
- Say one thing and mean it. If the line would be equally true under a different topic, it is wrong: rewrite it.
- No stacked abstractions. At most one abstract noun ("purpose", "potential", "greatness") per line, ideally none.

Sound like a person:
- Plain words a person would actually say. Banned: unlock, journey, embrace, elevate, unleash, harness, \
"in a world where", "the truth is", "it's not about X, it's about Y", "let that sink in".
- Nothing that would fit on a mug or a gym poster. No commands shouted at the reader, no exclamation marks.
- Concrete nouns and plain strong verbs over adjectives. Vary sentence length; let one sentence be short.
- No rhetorical questions stacked together, at most one comma-heavy sentence.

Craft rules:
- Write original lines only. Never quote or imitate a real person, never attribute a line to anyone. "author" is always null.
- The visual quote is short (ideally 5 to 16 words) and must stand alone on screen.
- The narration is the spoken version: 2 to 5 short sentences, 8 to 25 seconds aloud, natural rhythm, not the quote \
copied verbatim (it may end on the quote or a variation).
- Never produce variations of the same sentence across pieces. Vary structure, opening word, rhythm and intensity.
- Visual search queries are concrete, filmable stock-footage searches (subject + setting + light), 3 to 7 words, no \
brand names, no text-in-image requests.
- You never decide colors, font sizes, pixel positions, bitrates or crops.

Before you answer, reread your quote once. If it sounds like a caption an AI would generate, or it could be swapped \
into any other topic unchanged, throw it out and write the specific version instead.
Reply with a single JSON object and nothing else."""

# One voice per tone in app/settings.py. A bare tone word ("cinematic") means nothing to a model, so each entry says
# what the voice sounds like, the sentence shape it uses, and the failure it slides into when left to itself.
TONE_VOICES = {
    "cinematic": "Wide and visual, like voice-over laid over a slow shot. Present tense. One image carries the line "
                 "and nothing explains it afterwards. Avoid film-trailer grandeur, fate, destiny, epic scale.",
    "reflective": "Someone looking back at something already lived. Hindsight framing, a small admission, no advice. "
                  "Stop just short of the moral; do not summarise the lesson for the listener.",
    "calm": "Low and unhurried, from someone with nothing to prove. Short declarative sentences, ordinary words, no "
            "stakes and no urgency. Avoid instructing the listener, and avoid the word simply.",
    "intense": "Close up and under pressure. Short hard sentences, strong verbs, second person allowed. Name the cost "
               "rather than the reward. Avoid shouting, gym-poster commands, anything a coach would yell.",
    "inspirational": "Forward-leaning but grounded. Earn the lift with one concrete detail before the turn. No "
                     "promises, no you-can-do-anything. If it would fit on a motivational poster, rewrite it.",
    "conversational": "Talking to one person across a table. Contractions, a natural aside, slightly loose rhythm, "
                      "may start mid-thought. Avoid performing wisdom, and never address an audience or a crowd.",
    "emotional": "Close to the feeling without describing it. Name a concrete moment and let the emotion sit under "
                 "it. Do not name emotions outright (sad, proud, broken). No sentimentality, no swelling.",
    "minimal": "As few words as will hold the thought, usually one clause. Nothing decorative; an adjective must "
               "carry meaning or go. Avoid sounding cryptic, oracular or like a fortune cookie.",
    "thoughtful": "An idea being turned over, carrying one precise distinction. One qualifying clause allowed. Ends "
                  "on a shift in how the thing is seen, not on a conclusion. No rhetorical questions.",
}

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
    parts = [f"Topic: {b['topic']}", f"Tone: {b['tone']}. {TONE_VOICES.get(b['tone'], '')}".strip()]
    if b.get("mood"):
        parts.append(f"Mood: {b['mood']}")
    if b.get("audience"):
        parts.append(f"Audience: {b['audience']}")
    fmt = {"automatic": "choose video or image per piece, mostly video", "video": "all video",
           "image": "all image", "video_image": "every piece becomes both a video and an image, so prefer video footage"}
    parts.append(f"Output: {fmt[b['format']]}")
    parts.append("Platforms: " + ", ".join(b["platforms"]))
    if b.get("target_seconds"):
        parts.append(f"Narration target: about {b['target_seconds']} seconds aloud (roughly "
                     f"{round(b['target_seconds'] * 2.4)} words) - this overrides the default narration length")
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
