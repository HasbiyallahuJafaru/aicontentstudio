"""Build the bundled music library (owner 2026-11-12: the Commons classical beds "sound almost comical"; wanted:
slow piano that gives the words depth, a little strings, a deep anchor, nothing else). Every track is written by
Google Lyria 3 Pro through OpenRouter (~2 min, $0.08 a track, so the whole library is about $1 once), then
faded, loudness-matched to -20 LUFS and saved as small AAC files in assets/music/<genre>-<n>.m4a, with CREDITS.md.

Run once from apps/backend: .venv/Scripts/python scripts/make_music.py  (needs ffmpeg on PATH and the OpenRouter key
in <repo>/.env). Not run by the app. A track already built is skipped, so a rerun only fills the gaps; delete a file
to have it written again.
"""
import base64
import json
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.creative.model import BASE  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assets" / "music"
MODEL = "google/lyria-3-pro-preview"

# the shared bed every track is built on: the owner's brief, word for word where it can be
BED = ("A two-minute instrumental underscore to sit quietly under a deep male voice reading a quote. Slow felt piano "
       "(around 56-64 bpm), sparse, with space between the notes, a little soft sustained strings, and a deep low "
       "anchor (cello or double bass holding the root) underneath. Warm room reverb, close and intimate, cinematic. "
       "No drums, no percussion, no vocals, no choir, no synth leads, no plucked or bouncy rhythm, nothing playful, "
       "no big build or climax: steady and quiet from start to end so the voice always leads.")
TRACKS = {
    "hope-1": "Mood: hope after a long night. Gentle major-key piano chords, high soft violins entering slowly.",
    "hope-2": "Mood: tender and quietly uplifting. Piano melody in the middle register, warm viola pad, low cello.",
    "speech-1": "Mood: hard truth, grave and resolute. Low piano octaves, dark minor key, slow swelling low strings.",
    "speech-2": "Mood: discipline at dawn, serious and determined. Repeated low piano notes, cello and bass drone.",
    "stoic-1": "Mood: solemn and still, an old philosopher's calm. Minor-key piano, one cello line, long silences.",
    "stoic-2": "Mood: grounded acceptance. Open fifths on the piano, soft string pad, deep bass drone.",
    "history-1": "Mood: dignified and ancient, the weight of the past. Low strings and slow piano, minor key.",
    "history-2": "Mood: reverent remembrance. Sparse piano over a sustained cello and double bass, a hint of viola.",
    "books-1": "Mood: reading by lamplight, intimate and wise. Solo piano with a faint string pad.",
    "books-2": "Mood: reflective and warm. Soft piano arpeggios played slowly, low cello anchor, quiet violins.",
    "cinema-1": "Mood: minimal cinematic, open and spacious. Ambient piano with long reverb, sustained strings.",
    "cinema-2": "Mood: quiet melancholy, a film's last scene. Slow piano phrase repeated, low strings beneath.",
}


def lyria(prompt: str) -> bytes:
    """One track: audio output on OpenRouter only streams, base64 mp3 in the deltas."""
    chunks = []
    with httpx.stream("POST", BASE + "/chat/completions",
                      json={"model": MODEL, "modalities": ["audio", "text"], "stream": True,
                            "audio": {"format": "mp3"}, "messages": [{"role": "user", "content": prompt}]},
                      headers={"Authorization": f"Bearer {config.SECRETS['OPENROUTER_API_KEY']}"},
                      timeout=600, verify=ssl.create_default_context()) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            j = json.loads(line[6:])
            if "error" in j:
                raise RuntimeError(j["error"])
            for c in j.get("choices", []):
                if (a := c.get("delta", {}).get("audio") or {}).get("data"):
                    chunks.append(a["data"])
    if not chunks:
        raise RuntimeError("no audio came back")
    return base64.b64decode("".join(chunks))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, mood in TRACKS.items():
            out = OUT / f"{name}.m4a"
            if out.exists():
                continue
            raw = Path(tmp) / f"{name}.mp3"
            raw.write_bytes(lyria(f"{BED} {mood}"))
            length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                           "csv=p=0", str(raw)], capture_output=True, text=True, check=True).stdout)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af",
                            f"afade=t=in:d=2,afade=t=out:st={max(length - 4, 0):.2f}:d=4,loudnorm=I=-20:TP=-2:LRA=7",
                            "-ar", "44100", "-ac", "2", "-c:a", "aac", "-b:a", "96k", str(out)], check=True)
            print(name, f"{length:.0f}s", out.stat().st_size // 1024, "KiB", file=sys.stderr)
    lines = ["# Bundled music", "",
             "Every track was written for this app by Google Lyria 3 Pro (through OpenRouter) from the prompts in",
             "`scripts/make_music.py`: slow piano, soft strings and a low anchor, no drums or vocals. Built once by",
             "the developer; Google claims no ownership of generated output (Gemini API terms). Lyria marks its",
             "audio with an inaudible SynthID watermark.", "", "| File | Brief |", "|---|---|"]
    lines += [f"| {n}.m4a | {m} |" for n, m in TRACKS.items()]
    (OUT / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
