"""Non-secret settings. API keys live in Electron main (OS-encrypted), never here."""
from typing import Literal

from pydantic import BaseModel, Field

from app.database import connect

Tone = Literal["cinematic", "reflective", "calm", "intense", "inspirational",
               "conversational", "emotional", "minimal", "thoughtful"]


class Settings(BaseModel):
    ai_model: str = Field("deepseek-flash", min_length=1, max_length=64)
    ai_temperature: float = Field(1.0, ge=0, le=2)
    ai_max_tokens: int = Field(2000, ge=256, le=8192)
    default_topic: str = Field("discipline", min_length=1, max_length=60)
    default_tone: Tone = "cinematic"
    default_quantity: int = Field(6, ge=1, le=20)


def _load() -> Settings:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'app'").fetchone()
    return Settings.model_validate_json(row["value"]) if row else Settings()


def get() -> dict:
    return _load().model_dump()


def update(**changes) -> dict:
    merged = Settings.model_validate(_load().model_dump() | changes)
    with connect() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('app', ?) "
                     "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (merged.model_dump_json(),))
    return merged.model_dump()
