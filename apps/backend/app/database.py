import sqlite3
from pathlib import Path

from app import config

MIGRATIONS = Path(__file__).parent / "migrations"


def connect() -> sqlite3.Connection:
    """One short-lived connection per call; safe across the RPC thread pool."""
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate() -> None:
    """Apply migrations/NNN_*.sql in order, each once (tracked by PRAGMA user_version)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for path in sorted(MIGRATIONS.glob("*.sql")):
            n = int(path.name.split("_")[0])
            if n > current:
                conn.executescript(path.read_text(encoding="utf-8") + f"\nPRAGMA user_version = {n};")
