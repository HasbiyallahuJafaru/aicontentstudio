"""Whisper through OpenRouter over overlapping chunks: word-level times feed the karaoke captions, the cut snapping
and the dead-air cuts."""
import math
import ssl
import time

import httpx

from app.clipper.ff import duration_of, ffmpeg
from app.creative.model import BASE, api_key
from app.errors import UserError

# OpenRouter caps a request at 25 MB and its upstream providers at 60 s, so chunks stay short: 310 s of 16 kHz
# mono FLAC is ~10 MB and seconds of GPU time. The overlap past each seam keeps words cut at a seam whole.
CHUNK, OVERLAP = 300, 10
URL = BASE + "/audio/transcriptions"
# The cheapest Whisper on OpenRouter (2026-11-07: ~$0.012/audio hour via DeepInfra, ~$0.04 via Groq), and the same
# model the app used on Groq directly. OpenRouter picks the provider; transcription ignores routing preferences.
MODEL = "openai/whisper-large-v3-turbo"


def estimate_words(text: str, start: float, end: float) -> list[dict]:
    """Word timings spread over [start, end] by word length: for narration we wrote ourselves, and for a
    transcription provider that returns segments without word times."""
    tokens = text.split()
    total = sum(len(w) + 1 for w in tokens) or 1
    words, t = [], start
    for w in tokens:
        span = (end - start) * (len(w) + 1) / total
        words.append({"word": w, "start": round(t, 3), "end": round(min(t + span * 0.9, end), 3)})
        t += span
    return words


def stitch(transcript: dict, segments: list[dict], words: list[dict], offset: float, last: bool):
    """Append one chunk's results (times relative to the chunk) to the transcript. Chunks overlap past each seam,
    so a chunk keeps only items starting before its seam and skips items the previous chunk already covered."""
    seam = math.inf if last else offset + CHUNK
    for key, items in (("segments", segments), ("words", words)):
        kept = transcript[key]
        covered = kept[-1]["end"] - 0.05 if kept else -math.inf
        kept += [item | {"start": item["start"] + offset, "end": item["end"] + offset}
                 for item in items if covered <= item["start"] + offset < seam]


def transcribe(video, work) -> dict:
    """Returns {language, segments: [{start, end, text}], words: [{word, start, end}]}."""
    chunks = work / "audio"
    chunks.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {api_key('transcribe videos')}"}
    verify = ssl.create_default_context()  # Windows cert store: works behind TLS-inspecting local CAs
    transcript = {"language": None, "segments": [], "words": []}
    offsets = range(0, max(1, math.ceil(duration_of(video) - OVERLAP)), CHUNK)
    for offset in offsets:
        # Each chunk is its own complete file: ffmpeg's segment muxer writes FLAC pieces whose headers claim the
        # whole stream's length, and STT providers return 500 on those.
        chunk = chunks / f"{offset:05}.flac"
        ffmpeg("-ss", str(offset), "-t", str(CHUNK + OVERLAP), "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
               "-sample_fmt", "s16", "-c:a", "flac", str(chunk))
        r = _post(URL, headers, verify, chunk)
        transcript["language"] = transcript["language"] or r.get("language")
        segments = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in r.get("segments") or []]
        words = [{"word": w["word"].strip(), "start": w["start"], "end": w["end"]} for w in r.get("words") or []]
        if segments and not words:  # a provider without word times: estimate inside each segment, never fail
            words = [w for s in segments for w in estimate_words(s["text"], s["start"], s["end"])]
        stitch(transcript, segments, words, offset, last=offset == offsets[-1])
    return transcript


def _post(url: str, headers: dict, verify, chunk) -> dict:
    """One transcription call; bounded retries on network errors and 429/5xx, human errors on the rest."""
    body = ""
    for attempt in range(4):
        try:
            with open(chunk, "rb") as f:
                r = httpx.post(url, headers=headers, verify=verify, timeout=httpx.Timeout(300, connect=15),
                               data={"model": MODEL, "response_format": "verbose_json",
                                     "timestamp_granularities[]": ["word", "segment"]},
                               files={"file": (chunk.name, f, "audio/flac")})
        except httpx.HTTPError as e:
            body = repr(e)
            status = 0
        else:
            status, body = r.status_code, r.text[:300]
            if status == 401:
                raise UserError("OpenRouter authentication failed. Check your OpenRouter API key in Settings.", body)
            if status == 402:
                raise UserError("Your OpenRouter account is out of credits. Top it up, then try again.", body)
            if r.is_success:
                return r.json()
        if status and status < 500 and status != 429:
            break  # a 4xx we can't fix by retrying
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise UserError("Couldn't transcribe this video right now. Try again in a few minutes.", body)
