"""Projects: one creative brief (topic, tone, format, quantity, platforms). Content pieces attach in Milestone 2."""
import json
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.database import connect
from app.errors import UserError
from app.settings import Tone

Platform = Literal["youtube_shorts", "instagram_reels", "instagram_feed", "tiktok"]


class CreativeBrief(BaseModel):
    topic: str = Field(min_length=1, max_length=60)
    tone: Tone
    mood: str = Field("", max_length=80)
    audience: str = Field("", max_length=80)
    format: Literal["automatic", "video", "image", "video_image"] = "automatic"
    quantity: int = Field(ge=1, le=20)
    platforms: list[Platform] = Field(min_length=1)


def _row(r) -> dict:
    return {**dict(r), "brief": json.loads(r["brief"])}


def create(brief: dict) -> dict:
    b = CreativeBrief.model_validate(brief)
    b.topic = b.topic.strip()
    pid = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute("INSERT INTO projects (id, name, brief) VALUES (?, ?, ?)",
                     (pid, b.topic[:1].upper() + b.topic[1:], b.model_dump_json()))
    return get(pid)


def list_(limit: int = 200) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def get(id: str) -> dict:
    with connect() as conn:
        r = conn.execute("SELECT * FROM projects WHERE id = ?", (id,)).fetchone()
    if r is None:
        raise UserError("This project no longer exists.", f"project id {id}")
    return _row(r)


def delete(id: str) -> dict:
    with connect() as conn:
        n = conn.execute("DELETE FROM projects WHERE id = ?", (id,)).rowcount
    return {"deleted": n}
