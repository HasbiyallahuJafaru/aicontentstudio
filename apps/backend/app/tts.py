"""Narration (PRD §29): Google Gemini TTS through OpenRouter, on the same key as every other AI call, plus
ElevenLabs voices through the same key (owner 2026-11-12: "a deeper and raspier voice").

Gemini returns raw 16-bit PCM (it rejects mp3); the response's content type names the rate and channels, and the
stdlib wraps it as a WAV for the renderer. The piece's `delivery` note ("calm_reflective") becomes the read
direction. TTSProvider stays as the seam tests fake.
"""
import logging
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

log = logging.getLogger(__name__)

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
# Owner 2026-11-13: real speech is brisk overall and moves: quicker through the setup, easing off for a moment on
# the line that matters, then straight back up to speed. "Let a real silence fall after each sentence" made every
# read slow and even; slowing down is now the exception, kept for the one line that carries the point.
PACE = ("Natural conversational pace, a touch quicker than an average speaker, the way people really talk: let the "
        "speed rise and fall with the thought, move briskly through the setup, and slow down only once, on the line "
        "that carries the point, then pick the pace straight back up. Short breaths between sentences, never long "
        "silences. Real emotion; never sing-song, never an announcer, never a flat read.")
NARRATORS = {
    "elder": {"label": "Elder · wise grandfather", "voice": "Algenib",
              "persona": "You are an elderly man in your seventies, a grandfather who has lived a long life and "
                         "read every history book in his library. Deep, low, gravelly chest voice with warmth in it. "
                         "You are telling a story you love to someone young, sitting close by a fire.",
              "pace": "Easy storytelling pace, never dragging. Quiet awe on the surprising facts, gravity on the consequences, a "
                      "faint knowing smile in the voice on the irony."},
    "stoic": {"label": "Stoic · calm authority", "voice": "Charon",
              "persona": "You are a weathered old philosopher, deep-voiced and steady, speaking to one student. "
                         "Nothing rattles you; every word is chosen.",
              "pace": "Grounded and low in the chest, at an easy conversational pace. Calm certainty, never preachy; a hard line said softly."},
    "coach": {"label": "Hard truth · intense", "voice": "Alnilam",
              "persona": "You are a hardened mentor speaking to one person who is about to quit. Low, firm, close "
                         "to the microphone.",
              "pace": "Controlled intensity that builds sentence by sentence; short punches, then a held breath "
                      "before the line that matters. Never shouting."},
    "warm": {"label": "Warm · spoken word", "voice": "Sulafat",
             "persona": "You are a gentle spoken-word poet reading a letter to one listener late at night.",
             "pace": "Soft but present and flowing, never dragging; hope rising through the piece, never saccharine."},
    "storyteller": {"label": "Storyteller · documentary", "voice": "Rasalgethi",
                    "persona": "You are a documentary narrator with a rich, mature voice who loves this story.",
                    "pace": "Lively and vivid, curiosity in the voice; clear on names and dates."},
}
# ElevenLabs stock voices on OpenRouter (owner 2026-11-12: deeper and raspier). Eleven v4 takes no director's note:
# the voice itself carries the character (plus an inline audio tag), and pauses come from the text. A voiced quote
# is ~500 characters: ~2 cents on v4 Turbo, ~0.5 cents on Fish Drama, ~0.25 on Gemini.
# v4 Turbo since 2026-11-12 (owner: ElevenLabs "a bit too expensive"): the same voices and audio tags at half
# eleven-v4's price ($0.04 against $0.08 per 1000 characters, checked against a real read: 0.53 cents a line)
ELEVEN = "elevenlabs/eleven-v4-turbo"
# Fish Audio Drama 3 ($0.01 per 1000 characters, an eighth of eleven-v4): no stock voice, the voice is directed in
# plain words in square brackets (performed, never spoken: checked by transcription). Measured against the ElevenLabs
# grandpa on one line: the same depth (~101 Hz), slightly less rasp.
DRAMA = "fish-audio/drama-3"
# Owner 2026-11-12: "forced, too much energy, too much emphasis" - the age is in a low worn tone and an unhurried
# drawl, said plainly. "Warm and wise like a grandfather by the fire" invited a performance; this direction asks for
# the opposite. Measured on one line against that one: pitch 101 -> 72 Hz, pitch swing 3.5 -> 2.8 semitones,
# loudness swing 5.9 -> 4.1 dB (the flattest and most even of eight candidates), more rasp, a natural 1.9 words/s.
# 2026-11-13: asking him to "slow down only on the line that matters" slowed the whole read (2.0 words/s); this
# wording measured 2.1-2.3 words/s over two reads, the most fluid of three
ELDER = ("[an old man with a low raspy voice worn by age, talking casually and fluidly at a normal conversational "
         "speed, like he is telling a friend]")
NARRATORS.update({
    # owner 2026-11-12: "a grandpa's deep old raspy voice that speaks of wisdom". ElevenLabs' library voice made
    # for exactly that; measured ~104 Hz with the breathiest texture of nine candidates. `tag` is an eleven-v4
    # audio tag: performed, never spoken (checked by transcribing a tagged read).
    # the drawl is the age, so only a subtle lift (owner 2026-11-12: "subtly sped up"); 1.12 erased the drawl.
    # atempo keeps the pitch, so the voice stays as deep
    "grandpa": {"label": "Grandpa · old, deep and raspy (Fish Audio, lowest cost)", "model": DRAMA, "tag": ELDER,
                "tempo": 1.24},  # owner 2026-11-13: still too slow at 1.06 even after pause tightening; +17%
    "grandpa_premium": {"label": "Grandpa · premium (ElevenLabs)", "voice": "NOpBlnGInO9m6vDvFkFC",
                        "model": ELEVEN, "tag": "[quietly]"},  # [tired] dropped 2026-11-13: it slowed the whole read
    # MiniMax's deepest stock voice (~88 Hz): mp3 only on OpenRouter, decoded to WAV on arrival
    "bass": {"label": "Bass · very deep (MiniMax)", "voice": "English_ManWithDeepVoice",
             "model": "minimax/speech-2.8-hd", "format": "mp3"},
    "raspy": {"label": "Raspy · weathered storyteller (ElevenLabs)", "voice": "JBFqnCBsd6RMkjVDRZzb", "model": ELEVEN},
    "gravel": {"label": "Gravel · hard truth (ElevenLabs)", "voice": "2EiwWnXFnvU5JabPnv8n", "model": ELEVEN},
    "deep": {"label": "Deep · resonant (ElevenLabs)", "voice": "nPczCjzI2devNBz1zQrb", "model": ELEVEN},
    "sage": {"label": "Sage · old and wise (ElevenLabs)", "voice": "pqHfZKP75CvOlQylNhV4", "model": ELEVEN},
})
# a brief that picks no voice gets its genre's (2026-11-10: stoic used to fall to Gacrux, a female voice)
# owner 2026-11-13: the premium grandpa's pace is the best (talks quickly, short pauses for effect)
GENRE_VOICES = {"hope": "warm", "speech": "gravel", "stoic": "grandpa_premium", "cinema": "grandpa_premium",
                "history": "grandpa_premium", "books": "grandpa_premium"}
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
        if n.get("model"):  # ElevenLabs / MiniMax: same endpoint, no director's note (an inline tag at most)
            said = spoken(text)
            body = {"model": n["model"], "input": f"{n['tag']} {said}" if n.get("tag") else said,
                    "response_format": n.get("format", "pcm")}
            if n.get("voice"):  # Fish Drama is directed in the text, with no stock voice
                body["voice"] = n["voice"]
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
                    got = (_from_mp3(r.content) if body["response_format"] == "mp3"
                           else _wav(r.content, r.headers.get("content-type", "")))
                    return up_to_pace(tighten(_tempo(got, n["tempo"]) if n.get("tempo") else got), text)
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


def _tempo(audio: AudioResult, factor: float) -> AudioResult:
    """The narration played `factor` times faster, pitch kept (ffmpeg atempo), rewritten in place."""
    import subprocess
    src = Path(audio.path)
    out = src.with_name(src.stem + "-t.wav")
    try:
        subprocess.run([config.FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(src), "-af", f"atempo={factor:g}",
                        "-c:a", "pcm_s16le", str(out)], stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
                       check=True)
    except (subprocess.SubprocessError, OSError) as e:
        out.unlink(missing_ok=True)
        log.warning("tempo change skipped: %r", e)  # a slower read beats no read
        return audio
    out.replace(src)
    return AudioResult(src)


# Owner 2026-11-13: "slower than an average human would speak". Measured on a voiced quote: the voices talk at a
# normal 2.6-3.2 words/s, but 7-9 s of a 25-30 s read was silence (12-14 pauses, up to 1.3 s each), so the read
# averaged 1.9-2.3 words/s. Pauses are compressed on a curve, not capped: a short breath stays nearly as it was,
# a 1 s pause becomes ~0.5 s, and the rare long pause (the setup before the point) stays the longest, so the
# rhythm and its emphasis survive and the dead air goes.
PAUSE_MIN = 0.22   # a gap shorter than this is part of speech (stops, breaths between words): untouched
PAUSE_KEEP = 0.4   # of every second of pause past PAUSE_MIN, keep this share


def tighten(audio: AudioResult) -> AudioResult:
    """Shorten the narration's pauses in place (see PAUSE_KEEP); the voice itself is never touched."""
    import array
    with wave.open(str(audio.path), "rb") as w:
        params, pcm = w.getparams(), array.array("h", w.readframes(w.getnframes()))
    if params.sampwidth != 2 or not pcm:
        return audio
    step = params.framerate // 50 * params.nchannels  # 20 ms
    loud = [max(abs(min(pcm[i:i + step])), abs(max(pcm[i:i + step]))) for i in range(0, len(pcm), step)]
    if not max(loud):
        return audio
    floor = max(loud) * 0.04  # TTS is studio-clean: anything under 4% of the peak is silence
    out, i, n = array.array("h"), 0, len(loud)
    while i < n:
        j = i
        while j < n and loud[j] <= floor:
            j += 1
        if j > i:  # a run of silence from frame i to j
            gap = (j - i) * 0.02
            edge = i == 0 or j == n
            keep = gap if gap < PAUSE_MIN or edge else PAUSE_MIN + (gap - PAUSE_MIN) * PAUSE_KEEP
            k = round(keep / 0.02)
            # keep the silence's two ends (the voice's decay and the next intake), drop the middle
            head = (k + 1) // 2
            out.extend(pcm[i * step:(i + head) * step])
            out.extend(pcm[(j - (k - head)) * step:j * step])
            i = j
        else:
            while j < n and loud[j] > floor:
                j += 1
            out.extend(pcm[i * step:j * step])
            i = j
    with wave.open(str(audio.path), "wb") as w:
        w.setparams(params)
        w.writeframes(out.tobytes())
    return AudioResult(audio.path)


# a normal speaker runs ~2.5-2.8 words/s over a whole read, pauses included; one Fish Drama read measured 1.68 and
# the next 2.05 under the same direction, so a floor catches the slow ones instead of a fixed tempo for all
PACE_FLOOR = 2.45  # words/s
PACE_MAX_LIFT = 1.18  # beyond this atempo starts to sound sped up


def up_to_pace(audio: AudioResult, text: str) -> AudioResult:
    """Speed a read that came out slower than PACE_FLOOR up to it (pitch kept). The whole read scales evenly, so
    its own rises and falls of speed stay; a read already at pace is left alone."""
    words = len(spoken(text).split())
    rate = words / audio.duration if audio.duration else PACE_FLOOR
    if rate >= PACE_FLOOR or words < 12:  # a rate over a few words means nothing
        return audio
    return _tempo(audio, round(min(PACE_FLOOR / rate, PACE_MAX_LIFT), 3))


def _from_mp3(data: bytes) -> AudioResult:
    """An mp3 narration (MiniMax) as the same 24 kHz mono 16-bit WAV every other voice gives the renderer."""
    import subprocess
    out = config.MEDIA_DIR / "audio" / f"narration-{uuid.uuid4().hex[:12]}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    src = out.with_suffix(".mp3")
    src.write_bytes(data)
    try:
        subprocess.run([config.FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "24000",
                        "-c:a", "pcm_s16le", str(out)], stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
                       check=True)
    except (subprocess.SubprocessError, OSError) as e:
        raise UserError("The narration voice couldn't be prepared.", repr(e))
    finally:
        src.unlink(missing_ok=True)
    return AudioResult(out)


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
