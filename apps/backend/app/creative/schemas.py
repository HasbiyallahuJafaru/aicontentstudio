"""What the creative model must return. Everything is validated; nothing from the model is trusted as-is."""
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

Text = Annotated[str, AfterValidator(lambda s: " ".join(s.split()))]  # collapse stray whitespace/newlines
# narration keeps its line breaks: the prompt writes short lines and lets silence work, so each break is a pause
# the voice must hear (tts.spoken). Spaces collapse within a line, blank runs collapse to one break.
Lines = Annotated[str, AfterValidator(lambda s: "\n".join(" ".join(ln.split()) for ln in s.splitlines() if ln.strip()))]


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
    narration_style: Annotated[str, capped(60)] = ""  # video plans only; quote plans have nothing to narrate
    # documentaries only: the article's facts this piece is built on, none shared with another piece of the batch
    facts: Annotated[str, capped(700)] = ""

    @field_validator("facts", mode="before")
    @classmethod
    def _joined(cls, v):
        return " ".join(map(str, v)) if isinstance(v, list) else v  # models often send the facts as a list


class BatchPlan(BaseModel):
    # the planner's one-line reading of the topic; every piece is written against it (prompts.py)
    reading: Annotated[str, capped(300)] = ""
    # documentaries only: the planner's verdict that the topic IS the source article's subject (not a theme sharing
    # a word with it); false sends content.py back to a themed plan without the article
    subject: bool = False
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
    text: Text = Field(min_length=8, max_length=420)  # ~60 words: long passages welcome (owner 2026-11-10)
    author: str | None = None  # null for original lines; the real public-domain source for attributed genres
    # the book, speech or letter the line comes from (owner 2026-11-12: the voiced video says "Seneca once wrote", the
    # quote, then the book's name); null when the writer can't name the work for certain
    source: Annotated[str, capped(90)] | None = None


class Narration(BaseModel):
    # 3000: the longest length option (180 s at ~2.4 words a second, ~430 words) with room to spare. 700 failed
    # validation on every "~60 s" piece (144 words is already ~800 characters), killing the whole generation.
    text: Lines = Field(min_length=20, max_length=3000)
    # the director's note for this read (tts.direction): how the emotion moves through the piece
    delivery: Annotated[str, capped(200)] = Field(min_length=3)


class Shot(BaseModel):
    """One beat of the edit: what the camera is on while a given stretch of narration plays."""
    query: Annotated[str, capped(100)] = Field(min_length=3)
    role: Literal["literal", "metaphorical", "atmospheric", "archival"]  # archival: a Wikimedia Commons image


class Visual(BaseModel):
    preferred_type: Literal["video", "image"]
    search_query: Annotated[str, capped(100)] = Field(min_length=3)
    secondary_query: Annotated[str, capped(100)] = Field(min_length=3)
    mood: Annotated[str, capped(60)] = Field(min_length=3)
    # optional so a model that skips it degrades to the two flat queries instead of failing the whole piece
    # one per narration sentence (2026-11-10; was 4 beats, cycled to fill the voice); extra shots are trimmed
    shots: list[Shot] = Field(default_factory=list)

    @field_validator("shots")
    @classmethod
    def _at_most(cls, v: list) -> list:
        return v[:16]


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


class Callout(BaseModel):
    """A short phrase or number that punches on screen when the narration says `word`."""
    text: Annotated[str, capped(24)] = Field(min_length=1)
    word: Annotated[str, capped(30)] = Field(min_length=1)


class PieceContent(BaseModel):
    """A written piece. Quote images have no narration (nothing is spoken); VideoPieceContent requires it."""
    quote: Quote
    narration: Narration | None = None
    visual: Visual
    design: DesignHints | None = None  # narrated videos only; a quote image's design comes from the genre rotation
    metadata: Metadata
    # on-screen motion text (app/motion.py). Optional: pieces written before motion graphics still load.
    hook: Annotated[str, capped(70)] = ""
    callouts: list[Callout] = Field(default_factory=list)
    # voiced quote videos only: the spoken lesson on this exact quote, read after its author (prompts.LESSON)
    lesson: Annotated[str, capped(700)] = ""

    @field_validator("callouts")
    @classmethod
    def _two_at_most(cls, v: list) -> list:
        return v[:2]  # more is clutter; trimmed, not rejected, like every other over-long model field


class VideoPieceContent(PieceContent):
    """Anything that may become a video must carry the script it is cut to."""
    narration: Narration
    design: DesignHints
