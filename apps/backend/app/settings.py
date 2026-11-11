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
    # OpenRouter model ids. The writer: batch plans, pieces (with their metadata), clip picks and post copy.
    ai_model: str = Field("deepseek/deepseek-v4-pro", min_length=1, max_length=80)
    # The scanner: clip pass 1 reads a whole transcript (huge input, simple job), so the cheap model does it.
    ai_model_fast: str = Field("deepseek/deepseek-v4.1-flash", min_length=1, max_length=80)

    @field_validator("ai_model", "ai_model_fast", mode="before")
    @classmethod
    def _openrouter_id(cls, v):
        """Rows saved when the app called DeepSeek directly hold bare names; OpenRouter ids carry the vendor."""
        if isinstance(v, str) and v and "/" not in v:
            return {"deepseek-flash": "deepseek/deepseek-v4.1-flash"}.get(v, f"deepseek/{v}")
        return v

    ai_temperature: float = Field(1.0, ge=0, le=2)
    # a group of pieces + metadata, with room for a thinking model's reasoning (which shares this budget). The old
    # cap of 8192 was also the default, so the "raise AI max tokens" advice could never be followed (2026-11-09).
    ai_max_tokens: int = Field(16384, ge=256, le=32768)
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
    # Narration has no settings: Gemini TTS via OpenRouter (app/tts.py), voice picked per project on Create.
    # Rows saved with the old tts_* fields still load (pydantic ignores unknown keys).
    # PRD §67 music: the user's own licensed file, or the bundled public-domain library. Mixed quietly under the narration.
    music_path: str = Field("", max_length=500)
    music_volume: float = Field(0.15, ge=0, le=0.5)
    # no file set: play a public-domain track from the bundled library (owner 2026-11-10); off = silent bed
    bundled_music: bool = True
    # PRD §20: quality configurable under Advanced Settings. CRF 18-32 (lower = better, bigger files).
    render_crf: int = Field(18, ge=14, le=32)  # platforms re-encode on upload: give them a clean master
    render_audio_bitrate: str = Field("192k", pattern=r"^\d+k$")
    render_width: int = Field(1080, ge=360, le=2160)
    render_height: int = Field(1920, ge=640, le=3840)

    @field_validator("render_width", "render_height")
    @classmethod
    def _even(cls, v: int) -> int:
        return v - v % 2  # H.264 4:2:0 needs even sides: libx264 refuses 1081 outright
    # Animated hook titles and callouts (HyperFrames through Edge/Chrome). Off = plain edit, same as no browser.
    motion_graphics: bool = True
    # Clip downloads: a browser name (firefox, chrome, edge, ...) or a cookies.txt path, for YouTube's bot check.
    ytdlp_cookies: str = Field("", max_length=500)


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
