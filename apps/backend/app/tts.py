"""TTS (PRD §29): a replaceable provider interface with two local engines.

- WindowsTTS: the SAPI voices Windows already ships (offline, zero deps, instant) - the default.
- KokoroTTS: local neural voices via kokoro-onnx (much more natural). Optional: install with
  `pip install kokoro-onnx soundfile` and run `python -m app.tts download` to fetch the models.
"""
import asyncio
import json
import subprocess
import sys
import uuid
import wave
from pathlib import Path

from app import config
from app.errors import UserError

MODELS_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
MODEL_FILES = {"kokoro-v1.0.int8.onnx": 92, "voices-v1.0.bin": 26}  # download name: MB, for the download command
LOCAL_NAMES = {"voices-v1.0.bin": "voices.bin"}  # keep the old local name so existing installs stay valid


class AudioResult:
    def __init__(self, path: Path):
        self.path = path
        with wave.open(str(path), "rb") as w:
            self.duration = w.getnframes() / w.getframerate()


class TTSProvider:
    name = ""

    async def generate(self, text: str, voice: str, speed: float) -> AudioResult: ...


class WindowsTTS(TTSProvider):
    """SAPI voices through PowerShell: native, offline, no dependencies. Rate maps -10..10 <-> speed 0.5..2."""
    name = "windows"

    async def generate(self, text, voice, speed):
        out = config.MEDIA_DIR / "audio" / f"narration-{uuid.uuid4().hex[:12]}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        rate = max(-10, min(10, round((speed - 1) * 10)))
        script = (
            "Add-Type -AssemblyName System.Speech\n"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            f"$s.SetOutputToWaveFile('{out.as_posix()}')\n"
            + (f"$s.SelectVoice('{voice}')\n" if voice else "")
            + f"$s.Rate = {rate}\n"
            "$s.Speak([Console]::In.ReadToEnd())\n"
        )
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", script,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate(text.encode("utf-8"))
        if proc.returncode != 0 or not out.exists():
            raise UserError("Windows speech could not read the narration.", err.decode("utf-8", "replace")[-500:])
        return AudioResult(out)


class KokoroTTS(TTSProvider):
    """Local neural TTS via kokoro-onnx. Kokoro-82M quantized to int8 (~92 MB, CPU-friendly), Apache-2.0."""
    name = "kokoro"

    def __init__(self):
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError as e:
            raise UserError("The Kokoro voice engine is not installed.",
                            "Run: pip install kokoro-onnx soundfile  (in apps/backend/.venv)")
        if not self.model_path().exists():
            raise UserError("The Kokoro voice model is not downloaded yet.",
                            "Run: python -m app.tts download  (in apps/backend, with the venv active)")

    @staticmethod
    def model_path(name: str = "kokoro-v1.0.int8.onnx") -> Path:
        models = config.DATA_DIR / "models"
        legacy = models / "kokoro-v1.0.onnx"  # the fp32 download some earlier installs still have
        if name == "kokoro-v1.0.int8.onnx" and not (models / name).exists() and legacy.exists():
            return legacy
        return models / name

    async def generate(self, text, voice, speed):
        import kokoro_onnx
        import soundfile  # kokoro-onnx depends on it; imported here to keep it optional like kokoro itself
        kokoro = kokoro_onnx.Kokoro(str(self.model_path()), str(self.model_path("voices.bin")))
        out = config.MEDIA_DIR / "audio" / f"narration-{uuid.uuid4().hex[:12]}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = kokoro.create(text, voice=voice or "af_heart", speed=speed, lang="en-us")
        samples, rate = await result if asyncio.iscoroutine(result) else result  # api flipped sync in 0.6
        soundfile.write(out, samples, rate)
        return AudioResult(out)


def get_tts(provider: str | None = None) -> TTSProvider:
    from app import settings
    return {"windows": WindowsTTS, "kokoro": KokoroTTS}[provider or settings.get()["tts_provider"]]()


def download_models() -> None:
    """python -m app.tts download: fetch the quantized Kokoro onnx model + voices into the data dir."""
    import urllib.request
    target = config.DATA_DIR / "models"
    target.mkdir(parents=True, exist_ok=True)
    for name, mb in MODEL_FILES.items():
        dest = target / LOCAL_NAMES.get(name, name)
        if dest.exists():
            print(f"{dest.name}: already present")
            continue
        print(f"downloading {name} (~{mb} MB)...")
        urllib.request.urlretrieve(f"{MODELS_URL}/{name}", dest)
    print("done:", json.dumps({n: str(target / LOCAL_NAMES.get(n, n)) for n in MODEL_FILES}))


def voices() -> dict:
    """Narration voice options per engine, for the Create page picker. The optional engine simply contributes
    an empty list when it isn't installed/downloaded."""
    out = {"kokoro": [], "windows": _windows_voices()}
    try:
        import kokoro_onnx
        if KokoroTTS.model_path().exists():
            engine = kokoro_onnx.Kokoro(str(KokoroTTS.model_path()), str(KokoroTTS.model_path("voices.bin")))
            out["kokoro"] = sorted(engine.get_voices())
    except Exception:  # ponytail: voice listing must never break a settings call; empty list = not usable
        pass
    return out


def _windows_voices() -> list[str]:
    script = ("Add-Type -AssemblyName System.Speech\n"
              "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
              "ForEach-Object { $_.VoiceInfo.Name }")
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "download":
        download_models()
    else:
        print("usage: python -m app.tts download")
        sys.exit(1)
