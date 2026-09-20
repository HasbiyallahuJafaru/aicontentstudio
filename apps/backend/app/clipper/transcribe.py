"""Groq Whisper over overlapping chunks: word-level times feed the karaoke captions and the cut snapping."""
import math
import os
import ssl
import time

import httpx

from app import config
from app.clipper.ff import duration_of, ffmpeg
from app.errors import UserError

CHUNK, OVERLAP = 600, 10  # seconds of audio per STT request, plus overlap past each seam (Groq's chunking advice)
URL = os.environ.get("ACS_GROQ_URL", "https://api.groq.com/openai/v1") + "/audio/transcriptions"  # env: tests/proxies


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
    key = config.SECRETS.get("GROQ_API_KEY")
    if not key:
        raise UserError("Add your Groq API key in Settings to clip videos.")
    chunks = work / "audio"
    chunks.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {key}"}
    verify = ssl.create_default_context()  # Windows cert store: works behind TLS-inspecting local CAs
    transcript = {"language": None, "segments": [], "words": []}
    offsets = range(0, max(1, math.ceil(duration_of(video) - OVERLAP)), CHUNK)
    for offset in offsets:
        # Each chunk is its own complete file: ffmpeg's segment muxer writes FLAC pieces whose headers claim the
        # whole stream's length, and Groq returns 500 on those. 16 kHz mono s16 FLAC: 610 s <= 19.5 MB < 25 MB cap.
        chunk = chunks / f"{offset:05}.flac"
        ffmpeg("-ss", str(offset), "-t", str(CHUNK + OVERLAP), "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
               "-sample_fmt", "s16", "-c:a", "flac", str(chunk))
        r = _post(URL, headers, verify, chunk)
        transcript["language"] = transcript["language"] or r.get("language")
        stitch(transcript,
               [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in r.get("segments") or []],
               [{"word": w["word"].strip(), "start": w["start"], "end": w["end"]} for w in r.get("words") or []],
               offset, last=offset == offsets[-1])
    return transcript


def _post(url: str, headers: dict, verify, chunk) -> dict:
    """One Groq call; bounded retries on network errors and 429/5xx, human errors on the rest."""
    body = ""
    for attempt in range(4):
        try:
            with open(chunk, "rb") as f:
                r = httpx.post(url, headers=headers, verify=verify, timeout=httpx.Timeout(300, connect=15),
                               data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json",
                                     "timestamp_granularities[]": ["word", "segment"]},
                               files={"file": (chunk.name, f, "audio/flac")})
        except httpx.HTTPError as e:
            body = repr(e)
            status = 0
        else:
            status, body = r.status_code, r.text[:300]
            if status == 401:
                raise UserError("Groq authentication failed. Check your Groq API key in Settings.", body)
            if r.is_success:
                return r.json()
        if status and status < 500 and status != 429:
            break  # a 4xx we can't fix by retrying
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise UserError("Groq couldn't transcribe this video right now. Try again in a few minutes.", body)
