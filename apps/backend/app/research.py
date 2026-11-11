"""Facts for real subjects (owner 2026-11-10): a video about Mansa Musa must say who he was, not drift into a desert
poem. Before planning a narrated batch, the topic is looked up on Wikipedia (free, no key). When an article matches,
the planner reads it, decides whether the topic really is that subject (a person, place, event, work or thing) or a
theme that merely shares a word ("discipline"), and fact-mode pieces are written from this text only.

ponytail: English Wikipedia's plain-text intro + first sections, capped at MAX_CHARS. No other sources, no caching
beyond the process (lru_cache): one lookup per topic per run is cheap and the article rarely changes mid-session.
"""
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from functools import lru_cache

log = logging.getLogger("research")

API = os.environ.get("ACS_WIKI_API", "https://en.wikipedia.org/w/api.php")
UA = {"User-Agent": "AiContentStudio/0.1 (https://ytclipper.xyz; desktop app)"}  # Wikipedia refuses anonymous clients
MAX_CHARS = 6000   # one piece's worth: a life story's key facts; content.py asks for more per extra piece
MAX_WORDS = 7      # longer topics are sentences about a theme, never one article
STOP = {"the", "a", "an", "of", "and", "on", "in", "about", "for", "to", "story", "life", "history", "who", "was",
        "is", "video", "facts"}


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP}


def matches(topic: str, title: str) -> bool:
    """The article is plausibly the topic itself: every word of the title is in the topic (order free, so
    "Musa Mansa" finds "Mansa Musa") and the title covers most of the topic's own words."""
    t, a = _tokens(topic), _tokens(re.sub(r"\(.*?\)", "", title))
    return bool(a) and a <= t and len(a) / max(len(t), 1) >= 0.6


@lru_cache(maxsize=64)
def lookup(topic: str, max_chars: int = MAX_CHARS) -> dict | None:
    """{"title", "url", "description", "text"} for the article that is this topic, or None (no match, no network)."""
    topic = (topic or "").strip()
    if not topic or len(topic.split()) > MAX_WORDS or os.environ.get("ACS_NO_RESEARCH"):
        return None
    try:
        hits = _get({"action": "query", "list": "search", "srsearch": topic, "srlimit": 3,
                     "srprop": ""})["query"]["search"]
        title = next((h["title"] for h in hits if matches(topic, h["title"])), None)
        if title is None:
            return None
        page = _get({"action": "query", "prop": "extracts|description|info", "inprop": "url", "explaintext": 1,
                     "exsectionformat": "plain", "redirects": 1, "titles": title})["query"]["pages"][0]
    except Exception as e:  # noqa: BLE001 - research is a bonus: offline or blocked, the batch is written as before
        log.warning("wikipedia lookup for %r failed: %r", topic, e)
        return None
    text = page.get("extract") or ""
    # drop the reference tail and the blank-line noise; keep the opening sections, which carry the key facts
    text = re.split(r"\n(?:See also|References|Notes|Further reading|External links|Bibliography)\n", text)[0]
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if len(text) < 200 or "may refer to" in text[:300]:  # a stub or a disambiguation page tells us nothing
        return None
    return {"title": page["title"], "url": page.get("fullurl", ""), "description": page.get("description", ""),
            "text": text[:max_chars]}
