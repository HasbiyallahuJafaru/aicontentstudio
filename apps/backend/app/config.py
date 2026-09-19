import os
from pathlib import Path

VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[3]

# Electron passes ACS_DATA_DIR (userData/data when packaged); dev default is <repo>/data.
DATA_DIR = Path(os.environ.get("ACS_DATA_DIR") or REPO_ROOT / "data")
DB_PATH = DATA_DIR / "app.db"
MEDIA_DIR = DATA_DIR / "media"

# API keys, pushed by Electron main via "secrets.load". Dev fallback: <repo>/.env.
SECRETS: dict[str, str] = {}


def load_dotenv() -> None:
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#") and value.strip():
                SECRETS.setdefault(key.strip(), value.strip().strip('"'))


load_dotenv()
