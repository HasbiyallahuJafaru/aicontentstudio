"""What the creative model must return. Everything is validated; nothing from the model is trusted as-is."""
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

Text = Annotated[str, AfterValidator(lambda s: " ".join(s.split()))]  # collapse stray whitespace/newlines


def capped(max_len: int):
    """Collapse whitespace and cut to the cap instead of rejecting: an over-long model line must not fail a
    whole generation (real case: a 94-char angle)."""
    def check(s: str) -> str:
        s = " ".join(s.split())
        return s[:max_len].rstrip() or s
    return AfterValidator(check)


class PlanItem(BaseModel):
    angle: Annotated[str, capped(80)] = Field(min_length=3)
    visual_subject: Annotated[str, capped(80)] = Field(min_length=3)
    visual_type: Literal["video", "image"]
    intensity: Literal["low", "medium", "high"]
    narration_style: Annotated[str, capped(60)] = Field(min_length=3)


class BatchPlan(BaseModel):
    batch_theme: Annotated[str, capped(80)] = Field(min_length=1)
    pieces: list[PlanItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _distinct(self):
        for field in ("angle", "visual_subject"):
            values = [getattr(p, field).strip().lower() for p in self.pieces]
            if len(set(values)) != len(values):
                raise ValueError(f"every piece needs a different {field}")
        return self


class Quote(BaseModel):
    text: Text = Field(min_length=8, max_length=180)
    author: str | None = None  # null for original lines; the real public-domain source for attributed genres


class Narration(BaseModel):
    text: Text = Field(min_length=20, max_length=700)
    delivery: Annotated[str, capped(40)] = Field(min_length=3)


class Shot(BaseModel):
    """One beat of the edit: what the camera is on while a given stretch of narration plays."""
    query: Annotated[str, capped(100)] = Field(min_length=3)
    role: Literal["literal", "metaphorical", "atmospheric"]


class Visual(BaseModel):
    preferred_type: Literal["video", "image"]
    search_query: Annotated[str, capped(100)] = Field(min_length=3)
    secondary_query: Annotated[str, capped(100)] = Field(min_length=3)
    mood: Annotated[str, capped(60)] = Field(min_length=3)
    # optional so a model that skips it degrades to the two flat queries instead of failing the whole piece
    shots: list[Shot] = Field(default_factory=list, max_length=6)


class DesignHints(BaseModel):
    text_density: Literal["low", "medium", "high"]
    animation: Literal["still", "slow", "medium"]
    composition: Literal["editorial", "centered", "minimal", "bold"]


class Metadata(BaseModel):
    title: Annotated[str, capped(100)] = Field(min_length=3)
    description: str = Field(min_length=10, max_length=1000)
    caption: str = Field(min_length=10, max_length=2200)
    hashtags: list[str] = Field(min_length=3, max_length=15)
    keywords: list[str] = Field(min_length=3, max_length=15)
    alt_text: str = Field(min_length=10, max_length=300)

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        tags = ["#" + t.strip().lstrip("#").replace(" ", "") for t in v if t.strip().lstrip("#")]
        return list(dict.fromkeys(tags))


class PieceContent(BaseModel):
    quote: Quote
    narration: Narration
    visual: Visual
    design: DesignHints
    metadata: Metadata
