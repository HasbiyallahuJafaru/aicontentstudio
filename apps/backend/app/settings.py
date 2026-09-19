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
    # PRD §18: days a visually similar asset stays off limits after use. Same-asset reuse waits for the
    # pool to be exhausted regardless of this; the per-rule example values (7/3/3) collapse into one knob.
    asset_cooldown_days: int = Field(7, ge=0, le=365)
    # PRD §16 scoring weights. Until M4/M5 analysis exists, only relevance, visual_quality and novelty score
    # points; the rest stay at 0 (ponytail: they light up in place, no schema change needed).
    asset_weights: dict[str, float] = Field(
        default_factory=lambda: {"relevance": 0.30, "visual_quality": 0.20, "composition": 0.15, "brand": 0.15,
                                 "color": 0.10, "novelty": 0.05, "motion": 0.05})


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
