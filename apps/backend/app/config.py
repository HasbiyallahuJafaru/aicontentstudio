import os
from pathlib import Path

VERSION = "0.1.2"
REPO_ROOT = Path(__file__).resolve().parents[3]

# Electron passes ACS_DATA_DIR (userData/data when packaged); dev default is <repo>/data.
DATA_DIR = Path(os.environ.get("ACS_DATA_DIR") or REPO_ROOT / "data")
DB_PATH = DATA_DIR / "app.db"
# shortest finished clip, seconds (owner 2026-11-08: a minute). Only the smoke run lowers it, to clip a 12 s fixture.
# seconds of finished clip. 20, not 60 (2026-11-09): strong hook-and-payoff moments often run 20-45 s and
# Shorts/Reels reward completion; set 60 in Create for TikTok's Creator Rewards.
MIN_CLIP = float(os.environ.get("ACS_MIN_CLIP") or 60)  # owner 2026-11-10: every clip runs a full minute
MEDIA_DIR = DATA_DIR / "media"

# A packaged install ships its own ffmpeg and passes these; on a dev machine they fall back to PATH.
FFMPEG = os.environ.get("ACS_FFMPEG") or "ffmpeg"
FFPROBE = os.environ.get("ACS_FFPROBE") or "ffprobe"

# API keys, pushed by Electron main via "secrets.load". Dev fallback: <repo>/.env.
SECRETS: dict[str, str] = {}


def load_dotenv() -> None:
    env = REPO_ROOT / ".env"
    if env.exists() and not os.environ.get("ACS_NO_DOTENV"):  # the test suite must never see a developer's keys
        for line in env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#") and value.strip():
                SECRETS.setdefault(key.strip(), value.strip().strip('"'))


load_dotenv()
