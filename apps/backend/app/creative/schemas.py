"""What the creative model must return. Everything is validated; nothing from the model is trusted as-is."""
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

Text = Annotated[str, AfterValidator(lambda s: " ".join(s.split()))]  # collapse stray whitespace/newlines


class PlanItem(BaseModel):
    angle: str = Field(min_length=3, max_length=80)
    visual_subject: str = Field(min_length=3, max_length=80)
    visual_type: Literal["video", "image"]
    intensity: Literal["low", "medium", "high"]
    narration_style: str = Field(min_length=3, max_length=60)


class BatchPlan(BaseModel):
    batch_theme: str = Field(min_length=1, max_length=80)
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
    author: None = None  # original lines only: never attributed to a real or invented person


class Narration(BaseModel):
    text: Text = Field(min_length=20, max_length=700)
    delivery: str = Field(min_length=3, max_length=40)


class Visual(BaseModel):
    preferred_type: Literal["video", "image"]
    search_query: str = Field(min_length=3, max_length=100)
    secondary_query: str = Field(min_length=3, max_length=100)
    mood: str = Field(min_length=3, max_length=60)


class DesignHints(BaseModel):
    text_density: Literal["low", "medium", "high"]
    animation: Literal["still", "slow", "medium"]
    composition: Literal["editorial", "centered", "minimal", "bold"]


class Metadata(BaseModel):
    title: str = Field(min_length=3, max_length=100)
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
