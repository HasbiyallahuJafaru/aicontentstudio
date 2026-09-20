"""Prompts for the creative director. Provider-neutral chat messages; every reply must be a JSON object."""
import json

SYSTEM = """You write for a top-tier short-form motivation studio — the kind of page that stops a scroll on \
YouTube Shorts, TikTok and Instagram (spoken-word "hopecore" pages, MotivationHub-grade narration). Every piece is \
one original idea, written to be SPOKEN over cinematic b-roll, aimed at one person mid-scroll.

The craft:
- You are talking to ONE person. Use "you" and mean it. They are tired, and one honest line can stop them.
- The first line is the hook and it must land in the first breath: a hard truth, a specific moment, or a name for \
the thing they feel but never say out loud. No greetings, no setup, no "we all have days when".
- Concrete beats abstract, every time. "The alarm reads 4:52. The floor is cold. You go anyway." — never \
"Discipline is important." Use a moment, an object, an hour of the day, a thing the body does.
- Short lines. Fragments are fine. One idea per line. Let silence do work.
- Name the real feeling under it (shame, dread, quiet resolve, hope) before the turn. The shape is almost always: \
pain -> truth -> agency. It ends on ONE line worth screenshotting. That line is the quote.
- Sound like a person, never a poster. Banned: unlock, journey, embrace, elevate, unleash, harness, grind, \
"level up", "no excuses", "winner", "it's not about X, it's about Y", "let that sink in", stacked rhetorical \
questions, exclamation marks, anything a gym poster or a LinkedIn guru would say.
- At most one abstract noun per quote ("purpose", "greatness"); concrete nouns and plain strong verbs everywhere else.

Stay on the brief:
- The line must be recognisably about the given topic. Not ambition, not success, not "growth" in general.
- Write about something specific enough to picture: a moment, an object, an hour of the day, a thing someone does.
- Say one thing and mean it. If the line would be equally true under a different topic, it is wrong: rewrite it.

Integrity and format:
- Write original lines only. Never imitate a living person; "author" stays null unless the brief's genre uses
  real public-domain quotes, in which case follow its attribution rules exactly.
- The quote stands alone on screen: 3 to 16 words.
- The narration is the spoken script: natural rhythm with room to breathe, not the quote copied verbatim (it may \
end on the quote or a variation). It must OPEN on the hook.
- Never produce variations of the same sentence across pieces. Vary structure, opening word, rhythm and intensity.
- Visual search queries are cinematic, filmable stock-footage searches: subject + setting + light or motion — \
for example "lone runner city dawn slow motion", "storm waves ocean cliff drone", "empty gym night rain window". \
3 to 8 words, no brand names, no text-in-image requests.
- The piece is CUT, not illustrated: "shots" is the shot list the edit cuts between, 4 beats in narration order. Every shot is a different subject AND a different location - never the same place at another hour, never the same subject from another angle. Shot 1 is the hook: the most kinetic thing in the list, already in motion. Across the four use at least one "literal" (shows what the words say), one "metaphorical" (shows the feeling, not the words) and one "atmospheric" (sets the place and the weather). Order them to follow your own narration, beat by beat.
- You never decide colors, font sizes, pixel positions, bitrates or crops.

Before you answer, reread the first line and the quote once. If the first line wouldn't stop a scroll, or the quote \
could sit unchanged under a different topic, throw it out and write the specific version instead.
Reply with a single JSON object and nothing else."""

# Each genre is a top-performing motivational format (researched 2026-09-20). "voice" is what the writing sounds
# like; "attributed" genres quote REAL documented public-domain sources and name the author instead of writing
# original lines.
GENRES = {
    "hope": {"label": "Hope — spoken word", "attributed": False,
             "voice": "Hopecore spoken word: gentle, vulnerable, unhurried. Name the quiet battles nobody sees "
                      "(the door you closed, the call you didn't make, the mirror you avoided) and answer them "
                      "with earned hope, never toxic positivity. It reads like a letter to the listener's 2am self."},
    "speech": {"label": "Hard Truth — speech edit", "attributed": False,
               "voice": "Hard-truth speech edit, Goggins/Jocko energy: second person, present tense, high stakes. "
                        "Short hard sentences that escalate; name the excuse, name the cost; end by calling them "
                        "to hold the line. Attack what they're accepting, never who they are."},
    "stoic": {"label": "Stoic Wisdom", "attributed": False,
              "voice": "Stoic journal voice, Marcus Aurelius at night: calm, eternal, unimpressed by noise. "
                       "Control versus not-control, mortality as a tool, duty over feeling. Plain declaratives, "
                       "nothing trendy, no self-help vocabulary."},
    "history": {"label": "Historical Voices", "attributed": True,
                "voice": "Historical voices: documented words from public-domain figures — Marcus Aurelius, Seneca, "
                         "Epictetus, Lincoln, Theodore Roosevelt, Lao Tzu. The narration sets the moment the line "
                         "came from and translates it into the listener's ordinary day."},
    "books": {"label": "Book Wisdom", "attributed": True,
              "voice": "Book wisdom: documented lines from public-domain classics — Meditations, Seneca's Letters, "
                       "As a Man Thinketh, Walden, The Art of War. The narration bridges the classic idea into the "
                       "listener's real, ordinary life and lands on why it still cuts."},
    "cinema": {"label": "Cinematic Minimal", "attributed": False,
               "voice": "Cinematic minimal, Mateusz M style: the visuals carry it. Very few words, spaced out, each "
                        "one an image. No advice at all — atmosphere and one turning line, then silence."},
}

PLAN_SHAPE = {
    "batch_theme": "string",
    "pieces": [{"angle": "the emotional door this piece uses (e.g. 'the 4:52 alarm', 'a hard truth about quitting')",
                "visual_subject": "distinct filmable subject",
                "visual_type": "video|image", "intensity": "low|medium|high",
                "narration_style": "e.g. calm reflective, quiet urgent, warm conversational"}],
}

PIECE_SHAPE = {
    "quote": {"text": "string", "author": None},
    "narration": {"text": "string", "delivery": "e.g. calm_reflective"},
    "visual": {"preferred_type": "video|image", "search_query": "string", "secondary_query": "string", "mood": "string",
               "shots": [{"query": "stock search for this beat", "role": "literal|metaphorical|atmospheric"}]},
    "design": {"text_density": "low|medium|high", "animation": "still|slow|medium",
               "composition": "editorial|centered|minimal|bold"},
    "metadata": {"title": "short title, no hashtags", "description": "2-3 sentences", "caption": "social caption, 1-3 short lines",
                 "hashtags": ["#tag", "5-10 relevant tags"], "keywords": ["5-10 search keywords"],
                 "alt_text": "describes the visual for screen readers"},
}


def _brief(b: dict) -> str:
    genre = GENRES.get(b["tone"], GENRES["hope"])
    parts = [f"Topic: {b['topic']}", f"Genre: {genre['label']}. {genre['voice']}"]
    if genre["attributed"]:
        parts.append(
            "Attribution: this genre quotes REAL, documented, public-domain lines. quote.text must be the actual "
            "documented line (never invented, never paraphrased) and author = the source's name (for example "
            "'Marcus Aurelius', 'Seneca', 'James Allen, As a Man Thinketh'). Nothing published after 1929. The "
            "narration is your own words: set the moment, deliver the line, land why it still cuts today.")
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

Plan a batch of exactly {n} piece(s) on this topic. Each piece enters through a different emotional door (for \
example: a hard truth, a specific 4am-style moment, a quiet confession, self-respect, hope after loss) and gets a \
different cinematic visual subject and setting (no two pieces with the same subject or setting). The batch varies \
emotional intensity and every piece opens on a hook strong enough to stop a scroll. They should feel like one \
brand, never like duplicates.{_avoid(avoid)}

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
The narration's FIRST line is the hook — write it last if you have to, but open on it. The quote is the line people \
screenshot. Other pieces in the batch cover: {", ".join(siblings) or "none"}. Stay on this piece's angle.{_avoid(avoid)}

Write this piece. Return JSON shaped like: {json.dumps(PIECE_SHAPE)}"""},
    ]


def repair(error: str) -> str:
    return ("That reply did not match the required JSON shape. Validation errors:\n"
            f"{error[:1500]}\n\nReturn the corrected JSON object only, same content, fixed to the shape.")
