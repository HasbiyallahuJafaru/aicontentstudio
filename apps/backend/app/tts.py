"""Narration (PRD §29): Google Gemini TTS through OpenRouter, on the same key as every other AI call.

Gemini returns raw 16-bit PCM (it rejects mp3); the response's content type names the rate and channels, and the
stdlib wraps it as a WAV for the renderer. The piece's `delivery` note ("calm_reflective") becomes the read
direction. TTSProvider stays as the seam tests fake.
"""
import re
import ssl
import time
import uuid
import wave
from pathlib import Path

import httpx

from app import config
from app.creative.model import BASE, api_key
from app.errors import UserError

MODEL = "google/gemini-3.8-flash-tts"
# Gemini's prebuilt voices, with Google's one-word character for the picker. Verified on OpenRouter 2026-11-07
# (Charon answered; an unknown name is a 400, so only these are offered).
VOICES = {"Charon": "informative", "Kore": "firm", "Puck": "upbeat", "Fenrir": "excitable", "Orus": "firm",
          "Enceladus": "breathy", "Algenib": "gravelly", "Gacrux": "mature", "Sadaltager": "knowledgeable",
          "Iapetus": "clear", "Achird": "friendly", "Sulafat": "warm", "Aoede": "breezy", "Leda": "youthful",
          "Zephyr": "bright", "Despina": "smooth", "Vindemiatrix": "gentle", "Achernar": "soft"}
DEFAULT_VOICE = "Charon"
# a brief that picks no voice gets its genre's: one "informative" voice read every genre the same (2026-11-09)
GENRE_VOICES = {"hope": "Sulafat", "speech": "Algenib", "stoic": "Gacrux", "cinema": "Enceladus",
                "history": "Sadaltager", "books": "Sadaltager"}
RETRIES = 3


class AudioResult:
    def __init__(self, path: Path):
        self.path = path
        with wave.open(str(path), "rb") as w:
            self.duration = w.getnframes() / w.getframerate()


class TTSProvider:
    async def generate(self, text: str, voice: str, delivery: str = "") -> AudioResult: ...


def spoken(text: str) -> str:
    """The narration as the voice should read it: each written line is a beat, so a line with no closing
    punctuation gets a comma (a breath) and the lines run on as one text."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " ".join(ln if ln[-1] in ".!?,;:\u2026\u2014-\"'\u201d" else ln + "," for ln in lines)


class GeminiTTS(TTSProvider):
    async def generate(self, text, voice, delivery=""):
        body = {"model": MODEL, "input": spoken(text), "voice": voice if voice in VOICES else DEFAULT_VOICE,
                "response_format": "pcm",  # the only format Gemini TTS accepts
                "instructions": f"Short-form video narration. Delivery: {delivery.replace('_', ' ') or 'natural'}. "
                                "Human pacing with real pauses, never an announcer voice."}
        headers = {"Authorization": f"Bearer {api_key('narrate pieces')}"}
        detail = ""
        for attempt in range(RETRIES + 1):
            try:
                r = httpx.post(BASE + "/audio/speech", json=body, headers=headers, timeout=httpx.Timeout(180, connect=15),
                               verify=ssl.create_default_context())
            except httpx.HTTPError as e:
                detail, status = repr(e), 0
            else:
                status, detail = r.status_code, r.text[:300] if not r.is_success else ""
                if status == 401:
                    raise UserError("OpenRouter authentication failed. Check your OpenRouter API key in Settings.", detail)
                if status == 402:
                    raise UserError("Your OpenRouter account is out of credits. Top it up, then try again.", detail)
                if r.is_success and r.content:
                    return _wav(r.content, r.headers.get("content-type", ""))
            if status and status < 500 and status != 429:
                break
            if attempt < RETRIES:
                time.sleep(2 ** attempt)
        raise UserError("The narration voice couldn't be generated right now. Try again in a few minutes.", detail)


def _wav(pcm: bytes, content_type: str) -> AudioResult:
    """audio/pcm;rate=24000;channels=1 (16-bit) -> narration-<id>.wav."""
    rate = int((re.search(r"rate=(\d+)", content_type) or [0, 24000])[1])
    channels = int((re.search(r"channels=(\d+)", content_type) or [0, 1])[1])
    out = config.MEDIA_DIR / "audio" / f"narration-{uuid.uuid4().hex[:12]}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return AudioResult(out)


def get_tts() -> TTSProvider:
    return GeminiTTS()


def voices() -> list[dict]:
    """The Create/Preview narration picker."""
    return [{"value": name, "label": f"{name} · {kind}"} for name, kind in VOICES.items()]
