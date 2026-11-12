"""Narration (PRD §29): Google Gemini TTS through OpenRouter, on the same key as every other AI call, plus
ElevenLabs voices through the same key (owner 2026-11-12: "a deeper and raspier voice").

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
          "Zephyr": "bright", "Despina": "smooth", "Vindemiatrix": "gentle", "Achernar": "soft",
          # deep male voices, verified on OpenRouter 2026-11-10
          "Rasalgethi": "informative", "Schedar": "even", "Umbriel": "easy-going", "Alnilam": "firm"}
DEFAULT_VOICE = "Charon"
# Narrators (owner 2026-11-10: "the voice feels stale, soft, robotic"): a Gemini voice plus a full director's note.
# Gemini TTS follows a persona, a scene and delivery notes; a one-line "Delivery: calm" read every piece flat.
# The piece's own `delivery` (the writer's note on how the emotion moves) is added on top of the persona.
PACE = ("Lean on the words that matter: names, numbers, the turn. Let a real silence fall after each sentence so "
        "it lands. Real breath and real emotion; never sing-song, never an announcer, never a flat read.")
NARRATORS = {
    "elder": {"label": "Elder · wise grandfather", "voice": "Algenib",
              "persona": "You are an elderly man in your seventies, a grandfather who has lived a long life and "
                         "read every history book in his library. Deep, low, gravelly chest voice with warmth in it. "
                         "You are telling a story you love to someone young, sitting close by a fire.",
              "pace": "Unhurried and deliberate. Quiet awe on the surprising facts, gravity on the consequences, a "
                      "faint knowing smile in the voice on the irony."},
    "stoic": {"label": "Stoic · calm authority", "voice": "Charon",
              "persona": "You are a weathered old philosopher, deep-voiced and steady, speaking to one student. "
                         "Nothing rattles you; every word is chosen.",
              "pace": "Slow, grounded, low in the chest. Calm certainty, never preachy; a hard line said softly."},
    "coach": {"label": "Hard truth · intense", "voice": "Alnilam",
              "persona": "You are a hardened mentor speaking to one person who is about to quit. Low, firm, close "
                         "to the microphone.",
              "pace": "Controlled intensity that builds sentence by sentence; short punches, then a held breath "
                      "before the line that matters. Never shouting."},
    "warm": {"label": "Warm · spoken word", "voice": "Sulafat",
             "persona": "You are a gentle spoken-word poet reading a letter to one listener late at night.",
             "pace": "Soft but present, unhurried; hope rising slowly through the piece, never saccharine."},
    "storyteller": {"label": "Storyteller · documentary", "voice": "Rasalgethi",
                    "persona": "You are a documentary narrator with a rich, mature voice who loves this story.",
                    "pace": "Measured and vivid, curiosity in the voice; clear on names and dates."},
}
# ElevenLabs stock voices on OpenRouter (owner 2026-11-12: deeper and raspier). Eleven v4 takes no director's note:
# the voice itself carries the character, and pauses come from the text ("..." and line breaks). ~$0.08 per 1000
# characters against Gemini's ~$0.01, so a voiced quote (~500 characters) costs about 4 cents to read.
ELEVEN = "elevenlabs/eleven-v4"
NARRATORS.update({
    "raspy": {"label": "Raspy · weathered storyteller (ElevenLabs)", "voice": "JBFqnCBsd6RMkjVDRZzb", "model": ELEVEN},
    "gravel": {"label": "Gravel · hard truth (ElevenLabs)", "voice": "2EiwWnXFnvU5JabPnv8n", "model": ELEVEN},
    "deep": {"label": "Deep · resonant (ElevenLabs)", "voice": "nPczCjzI2devNBz1zQrb", "model": ELEVEN},
    "sage": {"label": "Sage · old and wise (ElevenLabs)", "voice": "pqHfZKP75CvOlQylNhV4", "model": ELEVEN},
})
# a brief that picks no voice gets its genre's (2026-11-10: stoic used to fall to Gacrux, a female voice)
GENRE_VOICES = {"hope": "warm", "speech": "gravel", "stoic": "raspy", "cinema": "deep",
                "history": "raspy", "books": "raspy"}
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
        n = NARRATORS.get(voice) or {}
        if n.get("model"):  # ElevenLabs: same endpoint and PCM shape, no director's note
            body = {"model": n["model"], "input": spoken(text), "voice": n["voice"], "response_format": "pcm"}
        else:
            gemini, instructions = direction(voice, delivery)
            body = {"model": MODEL, "input": spoken(text), "voice": gemini,
                    "response_format": "pcm",  # the only format Gemini TTS accepts
                    "instructions": instructions}
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


def direction(voice: str, delivery: str = "") -> tuple[str, str]:
    """(Gemini voice, director's note) for a narrator key or a bare Gemini voice name."""
    note = delivery.replace("_", " ").strip()
    n = NARRATORS.get(voice)
    if n is None or "persona" not in n:  # a bare Gemini name (an ElevenLabs narrator never reaches Gemini)
        return (voice if voice in VOICES else DEFAULT_VOICE,
                f"Short-form video narration. Delivery: {note or 'natural'}. {PACE}")
    return n["voice"], (f"{n['persona']}\nDelivery: {n['pace']}" + (f" For this piece: {note}." if note else "")
                        + f"\n{PACE}")


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
    return ([{"value": k, "label": n["label"]} for k, n in NARRATORS.items()]
            + [{"value": name, "label": f"{name} · {kind}"} for name, kind in VOICES.items()])
