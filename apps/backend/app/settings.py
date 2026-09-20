"""Non-secret settings. API keys live in Electron main (OS-encrypted), never here."""
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

from app.database import connect

# Genres modelled on the top-performing motivational formats (researched 2026-09-20): hopecore spoken word,
# hard-truth speech edits, stoicism, historical voices, book wisdom, cinematic minimal. Each carries its own
# voice spec in app/creative/prompts.py.
Genre = Literal["hope", "speech", "stoic", "history", "books", "cinema"]
_LEGACY_TONES = {"cinematic": "cinema", "reflective": "hope", "calm": "stoic", "intense": "speech",
                 "inspirational": "hope", "conversational": "hope", "emotional": "hope",
                 "minimal": "stoic", "thoughtful": "books"}


class Settings(BaseModel):
    ai_model: str = Field("deepseek-flash", min_length=1, max_length=64)
    ai_temperature: float = Field(1.0, ge=0, le=2)
    ai_max_tokens: int = Field(4000, ge=256, le=8192)  # a piece + its metadata, with room for a thinking model
    default_topic: str = Field("", max_length=60)  # blank: the Create page starts empty
    default_tone: Genre = "hope"

    @field_validator("default_tone", mode="before")
    @classmethod
    def _map_legacy_tone(cls, v):
        """Settings rows written before the tone->genre swap store old tone names; map them forward."""
        if isinstance(v, str):
            v = _LEGACY_TONES.get(v, v)
            return v if v in get_args(Genre) else "hope"
        return v
    default_quantity: int = Field(1, ge=1, le=20)
    # PRD §18: days a visually similar asset stays off limits after use. Same-asset reuse waits for the
    # pool to be exhausted regardless of this; the per-rule example values (7/3/3) collapse into one knob.
    asset_cooldown_days: int = Field(7, ge=0, le=365)
    # PRD §16 scoring weights. Until M4/M5 analysis exists, only relevance, visual_quality and novelty score
    # points; the rest stay at 0 (ponytail: they light up in place, no schema change needed).
    asset_weights: dict[str, float] = Field(
        default_factory=lambda: {"relevance": 0.30, "visual_quality": 0.20, "composition": 0.15, "brand": 0.15,
                                 "color": 0.10, "novelty": 0.05, "motion": 0.05})
    # PRD §49 TTS: provider, voice, speed, volume. 'kokoro' = the quantized local neural voices (default;
    # needs `python -m app.tts download` once, see app/tts.py). 'windows' = SAPI voices (always there, offline).
    tts_provider: Literal["windows", "kokoro"] = "kokoro"
    tts_voice: str = Field("am_adam", max_length=80)
    tts_speed: float = Field(1.0, ge=0.5, le=2)
    tts_volume: float = Field(1.0, ge=0, le=1)
    # PRD §67 music: user-supplied licensed file only; never downloaded. Mixed quietly under the narration.
    music_path: str = Field("", max_length=500)
    music_volume: float = Field(0.15, ge=0, le=0.5)
    # PRD §20: quality configurable under Advanced Settings. CRF 18-32 (lower = better, bigger files).
    render_crf: int = Field(22, ge=14, le=32)
    render_audio_bitrate: str = Field("192k", pattern=r"^\d+k$")
    render_width: int = Field(1080, ge=360, le=2160)
    render_height: int = Field(1920, ge=640, le=3840)
    # Milestone 7 Phase C: publishing. Buffer's public OAuth client id (no secret — PKCE), and the user's own
    # S3-compatible host for the videos Buffer publishes from (its keys live in the credentials table).
    buffer_client_id: str = Field("", max_length=120)
    publish_host_endpoint: str = Field("", max_length=300)
    publish_host_bucket: str = Field("", max_length=200)
    publish_host_public_url: str = Field("", max_length=300)
    publish_host_region: str = Field("auto", max_length=40)


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
