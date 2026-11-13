"""The bundled music library (owner 2026-11-10): public-domain / CC0 recordings, 75 s excerpts per genre, built by
scripts/make_music.py into assets/music (sources and licences in its CREDITS.md). A track from the user's own
Settings file always wins; this only fills the silence when none is set."""
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "assets" / "music"
VOLUME = 0.7  # tracks are mastered to -20 LUFS; ducked, the bed sits ~9 dB under the -16 LUFS voice (2026-11-12:
               # 0.32 plus a hard duck left the music inaudible under speech)
FALLBACK = {"": "history"}


def tracks(tone: str) -> list[Path]:
    return sorted(DIR.glob(f"{FALLBACK.get(tone, tone)}-*.m4a")) or sorted(DIR.glob("*.m4a"))


# clips are someone talking: only the quiet beds (piano, slow strings), never an overture under a podcast
CLIP_MOODS = ("stoic", "books", "cinema", "hope")
CLIP_VOLUME = 0.16  # ~ -36 LUFS against -14 LUFS speech: felt, not heard, so the clip still sounds like itself


def for_clip(n: int) -> Path | None:
    found = [t for m in CLIP_MOODS for t in tracks(m) if t.name.startswith(m)]
    return found[n % len(found)] if found else None


def pick(tone: str, n: int) -> Path | None:
    """The genre's tracks in turn, so piece 1 and piece 2 of a batch don't share a score."""
    found = tracks(tone)
    return found[n % len(found)] if found else None
