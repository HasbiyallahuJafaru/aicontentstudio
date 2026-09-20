"""TTS (PRD §29): a replaceable provider interface with two local engines.

- WindowsTTS: the SAPI voices Windows already ships (offline, zero deps, instant) - the default.
- KokoroTTS: local neural voices via kokoro-onnx (much more natural). Optional: install with
  `pip install kokoro-onnx soundfile` and run `python -m app.tts download` to fetch the models.
"""
import asyncio
import json
import sys
import uuid
import wave
from pathlib import Path

from app import config
from app.errors import UserError

MODELS_URL = "https://huggingface.co/Kokoro-82M/kokoro-v1.0.onnx/resolve/main"
MODEL_FILES = {"kokoro-v1.0.onnx": 327, "voices.bin": 26}  # name: MB, for the download command


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
    """Local neural TTS via kokoro-onnx. 82M params, CPU-friendly, Apache-2.0."""
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
    def model_path(name: str = "kokoro-v1.0.onnx") -> Path:
        return config.DATA_DIR / "models" / name

    async def generate(self, text, voice, speed):
        import kokoro_onnx
        import soundfile  # kokoro-onnx depends on it; imported here to keep it optional like kokoro itself
        kokoro = kokoro_onnx.Kokoro(str(self.model_path()), str(self.model_path("voices.bin")))
        out = config.MEDIA_DIR / "audio" / f"narration-{uuid.uuid4().hex[:12]}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        samples, rate = await kokoro.create(text, voice=voice or "af_heart", speed=speed, lang="en-us")
        soundfile.write(out, samples, rate)
        return AudioResult(out)


def get_tts() -> TTSProvider:
    from app import settings
    provider = settings.get()["tts_provider"]
    return {"windows": WindowsTTS, "kokoro": KokoroTTS}[provider]()


def download_models() -> None:
    """python -m app.tts download: fetch the Kokoro onnx model + voices into the data dir."""
    import urllib.request
    target = config.DATA_DIR / "models"
    target.mkdir(parents=True, exist_ok=True)
    for name, mb in MODEL_FILES.items():
        dest = target / name
        if dest.exists():
            print(f"{name}: already present")
            continue
        print(f"downloading {name} (~{mb} MB)...")
        urllib.request.urlretrieve(f"{MODELS_URL}/{name}", dest)
    print("done:", json.dumps({n: str(target / n) for n in MODEL_FILES}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "download":
        download_models()
    else:
        print("usage: python -m app.tts download")
        sys.exit(1)
