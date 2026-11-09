"""Prompts for the creative director. Provider-neutral chat messages; every reply must be a JSON object.

Two writers, one per kind of content (owner overhaul 2026-11-08: the old single prompt wrote an early-morning
narration script for every request, whatever the topic and whatever was being made):
- QUOTES: quote images. Quotes only: no narration, no story, no hook line, no shot list.
- VIDEO: narrated shorts. A spoken script cut to footage.
Both start from the same rule: the topic, read literally, is the brief. The planner writes down its reading of the
topic once ("reading") and every piece is written against it.
"""
import json

TOPIC_RULES = """The topic is the brief. Read it literally first: who or what it is about, and what about them it \
celebrates, questions or confronts. Then stay inside that reading.
- Every line must be recognisably about that exact subject, in the sense the user meant. Two examples of reading a \
topic: "the beauty of man and his adventure in nature" means people out in the wild (summits, rivers, trails, the \
open sea, nights under stars) and the awe, smallness and courage of it; "communication; anyone can persuade" means \
how people speak, listen and win others over. Neither means discipline, productivity or a pep talk.
- Never drift to a neighbouring theme. If a line would sit just as well under "motivation" in general, it is wrong.
- Draw every image from the topic's own world: its places, people, objects, weather, seasons and actions. Never \
from a stock self-help scene.
- Banned unless the topic itself asks for them: clock times and timestamps ("At 5:47 a.m.", "4am"), alarms, "you \
step outside", "for the first time this year", cold floors, mirrors, gyms, "when nobody is watching".
- Banned everywhere: unlock, journey, embrace, elevate, unleash, harness, grind, "level up", "no excuses", \
"winner", "it's not about X, it's about Y", "let that sink in", stacked rhetorical questions, exclamation marks, \
anything a gym poster or a LinkedIn guru would say."""

# Owner 2026-11-08: every quote carries a real reference. Quotes are never invented: each is a real, documented line
# from a public-domain source, and "author" always names who said or wrote it.
ATTRIBUTION = """- Every quote is REAL: a documented line said or written by a real person whose work is in the public \
domain (died before 1955, the words published before 1929). quote.text is the documented wording, never invented, \
never paraphrased, never "in the style of". quote.author is always that person's name ("Seneca", "Marcus Aurelius", \
"Ralph Waldo Emerson"); never null, never "Unknown", "Anonymous" or a made-up name. A translated line must use a \
translation published before 1929 (Marcus Aurelius: George Long 1862; Seneca: Gummere 1917-25; Epictetus: Long or \
Oldfather 1925; Lao Tzu: Legge 1891); never a modern translation (Hays, Campbell, Mitchell, Kaufmann) and never Rumi \
via Coleman Barks. A line you are not sure is genuine and correctly attributed is not fine: pick another.
- Pick the line for the topic: it must genuinely speak to the reading of the topic, not merely sound wise."""

INTEGRITY = f"""{ATTRIBUTION}
- Never imitate a living person.
- Never produce variations of the same sentence across pieces: vary structure, opening word, rhythm and length.
- You never decide colors, font sizes, pixel positions, bitrates or crops.
Reply with a single JSON object and nothing else."""

QUOTES_SYSTEM = f"""You are the head writer of a premium quote page: the kind whose lines get screenshotted, saved \
and reposted as images. You write QUOTES. There is no narration, no voice-over, no story, no script, no hook line \
and no shot list in this job.

{TOPIC_RULES}

You CHOOSE real quotes; you never write them. What makes a choice worth saving:
- One complete thought that stands alone on an image with nothing around it: 4 to 25 words. Quote a self-contained \
sentence or two from a longer passage rather than a fragment.
- A shape you can hear: balance, contrast, or a turn in the second half.
- Exact and alive, never a worn-out line everyone has seen a thousand times; prefer the less obvious line from a \
famous voice, or a strong line from a less famous one.
- A batch covers different facets of the topic and draws on different voices: no author twice in a batch unless \
the topic is that author.

The photo: one still photograph that shows the quote's world (subject + setting + light), portrait, with calm space \
for text. Searches are 3 to 8 words, no brand names, no text-in-image requests.

{INTEGRITY}"""

VIDEO_SYSTEM = f"""You write for a top-tier short-form studio: narrated shorts that stop a scroll on YouTube Shorts, \
TikTok and Instagram. Every piece is one original idea, written to be SPOKEN over cinematic b-roll, aimed at one \
person mid-scroll.

{TOPIC_RULES}

The craft:
- Talk to ONE person. Use "you" when the topic is about them; describe the subject plainly when it is not.
- The first line is the hook and lands in the first breath, at most 12 words: a striking truth, a vivid image, or \
one small, specific detail from the topic's world the listener has lived. No greetings, no setup, no "we all have \
days when", no "there's a kind of".
- Default length: 55 to 80 words (about 22 to 32 seconds aloud); Cinematic Minimal 25 to 45. Shorter beats longer.
- Hooks that lose the scroll: a vague tease ("this changed everything"), a command ("stop scrolling"), wordplay to \
decode, a slow build where the real hook is line three. The piece delivers exactly what the hook promised.
- Every line earns the next: show the "but" or "so" logic without starting lines with those words, never "and \
then". Turn the piece about a third of the way in so attention climbs.
- Concrete beats abstract: specific images from the topic's own world, never "X is important".
- One idea per line, written like speech: mostly full sentences of mixed length, at most two fragments. Each line \
break is a pause.
- It ends on ONE line worth screenshotting. That line is the quote: a REAL documented line (4 to 25 words) with \
its real author, chosen to fit the topic. You never write the quote yourself.
- The narration is your own spoken script, natural rhythm with room to breathe. It must OPEN on the hook and say \
the quote LAST, word for word. Never "as X once said" and never the author's name aloud: the author is credited in \
the caption. The last line should make the first line read differently on a rewatch.
- Visual searches are cinematic, filmable stock-footage searches from the topic's world: subject + setting + light \
or motion, 3 to 8 words, no brand names, no text-in-image requests.
- The piece is CUT, not illustrated: "shots" is the shot list the edit cuts between, 4 beats in narration order. \
Every shot is a different subject AND a different location. Shot 1 is the hook: the most kinetic thing in the \
list, already in motion. Across the four use at least one "literal" (shows what the words say), one \
"metaphorical" (shows the feeling) and one "atmospheric" (sets the place and the weather).

{INTEGRITY}"""

# Each genre is a top-performing format (researched 2026-09-20). "quote" is how its quote images read; "voice" is how
# its narration sounds. Every genre quotes REAL documented public-domain lines and names the author (owner
# 2026-11-08); "quote" says which voices suit it.
GENRES = {
    "hope": {"label": "Hope — spoken word",
             "quote": "Tender and hopeful lines: soft certainty, warmth earned through honesty, never toxic "
                      "positivity. Voices like Emily Dickinson, Walt Whitman, Victor Hugo, Ralph Waldo "
                      "Emerson, Henry David Thoreau, Rabindranath Tagore, Kahlil Gibran.",
             "voice": "Hopecore spoken word: gentle, vulnerable, unhurried. Open on one small, specific detail from the "
                      "topic's world (an object, a place, a gesture) the listener has lived; hope comes from that "
                      "detail turning, never from reassurance. Banned: 'nobody sees', 'a kind of tired', 'it's "
                      "okay to', 'you're not alone'. It reads like a letter to the listener."},
    "speech": {"label": "Hard Truth — speech edit",
               "quote": "Blunt, hard-edged lines: a truth or a challenge that does not soften itself. Voices like "
                        "Theodore Roosevelt, Frederick Douglass, Seneca, Epictetus, Friedrich Nietzsche, Booker T. "
                        "Washington.",
               "voice": "Hard-truth speech edit: second person, present tense, high stakes. Short hard sentences "
                        "that escalate through concrete costs specific to the topic. End on a decision the "
                        "listener can make today, in your own words (never 'hold the line', 'stay hard', 'get "
                        "after it')."},
    "stoic": {"label": "Stoic Wisdom",
              "quote": "Calm, timeless Stoic lines: plain declaratives, unimpressed by noise. Marcus Aurelius, Seneca, "
                       "Epictetus, Musonius Rufus, Zeno of Citium, Cato, Cicero.",
              "voice": "Stoic journal voice: calm, eternal, unimpressed by noise. A Stoic's lens on THIS topic: "
                       "what a Stoic would notice about it, said plainly. Use the dichotomy of control or mortality "
                       "only when the topic invites it. Plain declaratives, no self-help vocabulary."},
    "history": {"label": "Historical Voices",
                "quote": "Real documented words from public-domain figures that genuinely speak to the topic.",
                "voice": "Historical voices: documented words from public-domain figures. The narration may name the "
                         "work and roughly when, only when certain; it never invents where or to whom a line was "
                         "said. It brings the line to the topic at hand."},
    "books": {"label": "Book Wisdom",
              "quote": "Real documented lines from public-domain classics that genuinely speak to the topic.",
              "voice": "Book wisdom: documented lines from public-domain classics. The narration bridges the classic "
                       "idea to the topic and lands on why it still holds."},
    "cinema": {"label": "Cinematic Minimal",
               "quote": "Spare, imagistic lines: few words, each one an image, no advice. Voices like Lao Tzu, Basho, "
                        "Rumi, Emily Dickinson, Henry David Thoreau, John Muir, Rainer Maria Rilke, Virginia Woolf.",
               "voice": "Cinematic minimal: the visuals carry it. Very few words, spaced out, each one an image. No "
                        "advice at all: atmosphere and one turning line, then silence."},
}

READING = ("one sentence: what this topic is about, in the user's sense, and what the batch will celebrate, "
           "question or confront")
QUOTES_PLAN_SHAPE = {
    "reading": READING,
    "batch_theme": "short name for the batch",
    "pieces": [{"angle": "a distinct facet of the topic this quote covers",
                "visual_subject": "a photographable subject and setting from the topic's world",
                "visual_type": "image", "intensity": "low|medium|high"}],
}
VIDEO_PLAN_SHAPE = {
    "reading": READING,
    "batch_theme": "short name for the batch",
    "pieces": [{"angle": "the distinct facet or emotional door of the topic this piece uses",
                "visual_subject": "a filmable subject and setting from the topic's world",
                "visual_type": "video|image", "intensity": "low|medium|high",
                "narration_style": "e.g. calm reflective, quiet urgent, warm conversational"}],
}

QUOTE_FIELD = {"text": "the real documented line", "author": "the real person who said or wrote it"}
DESIGN_FIELD = {"text_density": "low|medium|high", "animation": "still|slow|medium",
                "composition": "editorial|centered|minimal|bold"}
METADATA_FIELD = {"title": "what someone would type to find this, max 60 characters, no hashtags, e.g. "
                           "'Marcus Aurelius on being ignored'",
                  "description": "YouTube: 1-2 sentences, naming the quote's author and the work it comes from",
                  "caption": "social caption, 1-3 short lines. Line 1 is the searchable phrase in plain words; then "
                             "a detail the visual doesn't show, and credit the quote's author. Most captions need no "
                             "ask: at most 1 in 3 per batch ends on one (save it, or send it to a specific kind of "
                             "person), never two alike. Never 'follow for more', 'like if', 'tag a friend', "
                             "'comment YES'",
                  "hashtags": ["#tag", "3-5 niche, specific tags about the topic; never #fyp #viral #explore"],
                  "keywords": ["5-10 search keywords"],
                  "alt_text": "describes the visual for screen readers"}
QUOTE_PIECE_SHAPE = {
    "quote": QUOTE_FIELD,
    "visual": {"preferred_type": "image", "search_query": "the photo search", "secondary_query": "a different "
               "photo search for the same quote, used only if the first finds nothing", "mood": "string"},
    "metadata": METADATA_FIELD,
}
VIDEO_PIECE_SHAPE = {
    "quote": QUOTE_FIELD,
    "narration": {"text": "string", "delivery": "e.g. calm_reflective"},
    "visual": {"preferred_type": "video|image", "search_query": "string", "secondary_query": "string", "mood": "string",
               "shots": [{"query": "stock search for this beat", "role": "literal|metaphorical|atmospheric"}]},
    "design": DESIGN_FIELD,
    "metadata": METADATA_FIELD,
    "hook": "on-screen title for the first 2.5 s, max 7 words, 1-2 key words wrapped in *asterisks*",
    "callouts": [{"text": "max 3 words or a number", "word": "the narration word it lands on"}],
}


def quotes_only(brief: dict) -> bool:
    """Quote images: the brief makes images and nothing else, so nothing is ever narrated."""
    return brief.get("format") in ("image", "image_voiced")


def _brief(b: dict) -> str:
    genre = GENRES.get(b["tone"], GENRES["hope"])
    quotes = quotes_only(b)
    parts = [f'Topic: "{b["topic"]}"',
             f"Genre: {genre['label']}. {genre['quote'] if quotes else genre['voice']}"]
    if not b.get("given_quote") and not b.get("quotes"):  # the user's own lines are never swapped for "real" ones
        parts.append("Quote: a REAL documented public-domain line that genuinely speaks to the topic, with its real "
                     "author's name in quote.author (never null).")
    if b.get("mood"):
        parts.append(f"Mood: {b['mood']}")
    if b.get("audience"):
        parts.append(f"Audience: {b['audience']}")
    if not quotes:
        fmt = {"automatic": "choose video or image per piece, mostly video", "video": "all video",
               "video_image": "every piece becomes both a video and an image, so prefer video footage"}
        parts.append(f"Output: {fmt.get(b['format'], 'video')}")
    parts.append("Platforms: " + ", ".join(b["platforms"]))
    if b.get("quotes") and not b.get("given_quote"):
        parts.append("The user supplied the quotes, one per piece in this order. Plan each piece around its quote:\n"
                     + "\n".join(f"{i}. {q}" for i, q in enumerate(b["quotes"], 1)))
    if b.get("given_quote"):
        parts.append(f"This piece's quote is fixed, written by the user: \"{b['given_quote']}\". quote.text must be "
                     f'exactly that, word for word; author = {json.dumps(b.get("given_author"))}. Write everything '
                     "else around it.")
        if not b.get("given_author"):
            parts.append("This line has no author. Never name or imply one, in the narration or anywhere else.")
    if b.get("target_seconds") and not quotes:
        parts.append(f"Narration target: about {b['target_seconds']} seconds aloud (roughly "
                     f"{round(b['target_seconds'] * 2.4)} words) - this overrides the default narration length")
    return "\n".join(parts)


def verify(quotes: list[tuple[str, str]]) -> list[dict]:
    """Q1 (2026-11-09): a cheap second opinion on each "real" quote before it is kept."""
    lines = "\n".join(f'{i}. "{q}" - {a}' for i, (q, a) in enumerate(quotes, 1))
    return [{"role": "system", "content": "You check quotations for a publisher. Be strict about attribution."},
            {"role": "user", "content": f"""For each numbered quote, is it a genuine, documented line by the named \
author? Translation wording may differ slightly. Answer "no" if it is invented, a paraphrase presented as a quote, or \
misattributed (a well-known misattribution is "no"). Answer "unsure" if you can't tell.

{lines}

Return JSON: {{"verdicts": ["yes" | "no" | "unsure", ...]}}, one per quote, in order."""}]


def _avoid(avoid: list[str]) -> str:
    return ("\n\nRecently used lines. Do not repeat or closely paraphrase any of them:\n" + "\n".join(f"- {a}" for a in avoid)) if avoid else ""


def plan(brief: dict, avoid: list[str]) -> list[dict]:
    n = brief["quantity"]
    if quotes_only(brief):
        ask = (f"Plan a batch of exactly {n} quote(s) on this topic. First write your reading of the topic. Then give "
               "each quote a different facet of it (what it notices, admires, questions or warns about) and a "
               "different photographable subject and setting from the topic's world. The batch varies intensity "
               "and form, and reads as one series, never as duplicates.")
        shape = QUOTES_PLAN_SHAPE
    else:
        ask = (f"Plan a batch of exactly {n} narrated piece(s) on this topic. First write your reading of the topic. "
               "Then give each piece a different facet or emotional door into it (for example a striking truth, a "
               "quiet confession, a moment of awe, a turning point, a loss, a victory) and a different filmable "
               "subject and setting from the topic's world. The batch varies intensity and every piece opens on a "
               "hook strong enough to stop a scroll.")
        shape = VIDEO_PLAN_SHAPE
    return [
        {"role": "system", "content": QUOTES_SYSTEM if quotes_only(brief) else VIDEO_SYSTEM},
        {"role": "user", "content": f"""{_brief(brief)}

{ask}{_avoid(avoid)}

Return JSON shaped like: {json.dumps(shape)} with exactly {n} item(s) in "pieces"."""},
    ]


def piece(brief: dict, plan, item, avoid: list[str]) -> list[dict]:
    siblings = [p.angle for p in plan.pieces if p.angle != item.angle]
    reading = getattr(plan, "reading", "") or f'the topic "{brief["topic"]}", read literally'
    head = f"""{_brief(brief)}

Reading of the topic (stay inside it): {reading}""" + (
        f"\nBatch: {plan.batch_theme}. Other pieces cover: {', '.join(siblings)}." if siblings else "")
    if quotes_only(brief):
        facet = f' on the facet "{item.angle}"' if item.angle and item.angle != "quote" else ""
        subject = (f', photo subject "{item.visual_subject}"'
                   if item.visual_subject and item.visual_subject != brief["topic"] else "")
        ask = f"""Write one quote{facet}{subject}, intensity {item.intensity}: the quote, its photo search and its post \
copy. No narration, no script.{_avoid(avoid)}

Before you answer, check the quote against the reading above. If it drifted to a neighbouring theme, or would sit \
unchanged under a different topic, rewrite it.
Return JSON shaped like: {json.dumps(QUOTE_PIECE_SHAPE)}"""
    else:
        ask = f"""This piece: facet "{item.angle}", visual subject "{item.visual_subject}", preferred visual \
{item.visual_type}, intensity {item.intensity}, narration style {item.narration_style or "natural"}.
The narration's FIRST line is the hook. The quote is the line people screenshot. The "hook" is the animated title \
on screen while the first line is spoken: read with the sound off, it must stop the scroll alone (not a copy of the \
first line; a sharper promise or question). "callouts": 0-2 short phrases or numbers worth seeing, each tied to one \
word the narration actually says; leave it empty rather than decorate.{_avoid(avoid)}

Before you answer, check the first line and the quote against the reading above. If either drifted to a \
neighbouring theme, or would sit unchanged under a different topic, rewrite it.
Return JSON shaped like: {json.dumps(VIDEO_PIECE_SHAPE)}"""
    return [{"role": "system", "content": QUOTES_SYSTEM if quotes_only(brief) else VIDEO_SYSTEM},
            {"role": "user", "content": f"{head}\n{ask}"}]


def pieces(brief: dict, plan, items: list, avoid: list[str], given: list) -> list[dict]:
    """Several pieces in one request (owner 2026-11-08: batch instead of one call per piece). `given[j]` is the
    user's own (text, author) for item j, or None when the AI writes the quote."""
    reading = getattr(plan, "reading", "") or f'the topic "{brief["topic"]}", read literally'
    quotes = quotes_only(brief)
    rows = []
    for j, (item, own) in enumerate(zip(items, given), 1):
        if quotes:  # quote images are not planned (owner 2026-11-08): each row is just "a new quote" or the user's
            row = f"{j}. a new quote: its own facet of the topic and its own photographable subject from its world"
        else:
            row = (f'{j}. facet "{item.angle}", visual subject "{item.visual_subject}", intensity {item.intensity}, '
                   f"preferred visual {item.visual_type}, narration style {item.narration_style or 'natural'}")
        if own:
            row = (f'{j}. the user\'s quote, fixed: "{own[0]}"; quote.text must be exactly that, word for word; '
                   f"author = {json.dumps(own[1])}. Write its photo search and post copy around it")
        rows.append(row)
    if quotes:
        rules = "For each: the quote, its photo search, design hints and post copy. No narration, no script."
        shape = QUOTE_PIECE_SHAPE
    else:
        rules = ("For each: the narration's FIRST line is the hook; the quote is the line people screenshot; \"hook\" "
                 "is the animated title on screen while the first line is spoken (read with the sound off it must stop "
                 "the scroll alone, not a copy of the first line); \"callouts\": 0-2 short phrases or numbers worth "
                 "seeing, each tied to one word the narration actually says, or empty.")
        shape = VIDEO_PIECE_SHAPE
    n = len(items)
    return [{"role": "system", "content": QUOTES_SYSTEM if quotes else VIDEO_SYSTEM},
            {"role": "user", "content": f"""{_brief(brief)}

Reading of the topic (stay inside it): {reading}
Batch: {plan.batch_theme}.

Write these {n} piece(s), one per line below, in this order:
{chr(10).join(rows)}

{rules} Every piece is distinct from the others here: no two quotes or openings alike.{_avoid(avoid)}

Before you answer, check every piece against the reading above. If one drifted to a neighbouring theme, or would sit \
unchanged under a different topic, rewrite it.
Return JSON shaped like: {{"pieces": [{json.dumps(shape)}]}} with exactly {n} item(s) in "pieces", in the order above."""}]


def repair(error: str) -> str:
    return ("That reply did not match the required JSON shape. Validation errors:\n"
            f"{error[:1500]}\n\nReturn the corrected JSON object only, same content, fixed to the shape.")
