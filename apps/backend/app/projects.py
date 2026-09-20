"""Projects: one creative brief (topic, tone, format, quantity, platforms). Content pieces attach in Milestone 2."""
import json
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.database import connect
from app.errors import UserError
from app.settings import Genre as Tone

Platform = Literal["youtube_shorts", "instagram_reels", "instagram_feed", "tiktok"]


class CreativeBrief(BaseModel):
    topic: str = Field(min_length=1, max_length=60)
    tone: Tone
    mood: str = Field("", max_length=80)
    audience: str = Field("", max_length=80)
    format: Literal["automatic", "video", "image", "video_image"] = "automatic"
    quantity: int = Field(ge=1, le=20)
    platforms: list[Platform] = Field(min_length=1)
    voice: str = Field("", max_length=120)  # "engine:voice" from the Create picker; empty = Settings default
    fps: Literal[30, 60] = 30
    target_seconds: int | None = Field(None, ge=10, le=180)  # narration length target; None = writer's default
    subtitles: bool = False                   # burn spoken-word subtitles into rendered videos
    look_filter: Literal["auto", "none", "warm", "cool", "mono", "vivid"] = "auto"  # auto = the genre's grade
    blur_background: bool = False             # blurred full-bleed background, sharp centred footage
    parallax: bool = False                    # slow push-in on video pieces (stills always push in)


class ClipBrief(BaseModel):
    """A clip project cuts one long video into captioned shorts instead of writing content."""
    kind: Literal["clip"] = "clip"
    source: str = Field(min_length=1, max_length=500)  # http(s) URL or a local file path
    n: int | None = Field(None, ge=1, le=30)  # None = about one clip per minute of source
    min_len: float = Field(30, ge=5, le=600)
    max_len: float = Field(60, ge=10, le=900)
    orientation: Literal["9:16", "16:9", "1:1"] = "9:16"
    burn_captions: bool = True
    fps: Literal[30, 60] = 30


def _row(r) -> dict:
    return {**dict(r), "brief": json.loads(r["brief"])}


def create(brief: dict) -> dict:
    brief = brief or {}
    if brief.get("kind") == "clip":
        return _create_clip(ClipBrief.model_validate(brief))
    b = CreativeBrief.model_validate(brief)
    b.topic = b.topic.strip()
    pid = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute("INSERT INTO projects (id, name, brief) VALUES (?, ?, ?)",
                     (pid, b.topic[:1].upper() + b.topic[1:], b.model_dump_json()))
    return get(pid)


def _create_clip(b: ClipBrief) -> dict:
    source = b.source.strip()
    b.source = source
    is_url = source.startswith(("http://", "https://"))
    if not is_url and not Path(source).is_file():
        raise UserError("Enter a video URL or a file path that exists on this computer.", source)
    name = source.rstrip("/").rsplit("/", 1)[-1] if is_url else Path(source).stem
    pid = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute("INSERT INTO projects (id, name, brief) VALUES (?, ?, ?)",
                     (pid, name[:80], b.model_dump_json()))
    return get(pid)


def set_voice(project_id: str, voice: str) -> dict:
    """Swaps the project's narration voice after the fact (Preview modal); takes effect on the next render."""
    p = get(project_id)
    if p["brief"].get("kind") == "clip":
        raise UserError("Clip projects use the source video's own audio.")
    p["brief"]["voice"] = (voice or "").strip()[:120]
    with connect() as conn:
        conn.execute("UPDATE projects SET brief = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                     (json.dumps(p["brief"], ensure_ascii=False), project_id))
    return get(project_id)


def list_(limit: int = 200) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT p.*, (SELECT count(*) FROM content_pieces c WHERE c.project_id = p.id AND c.status != 'failed')"
                            " AS pieces_written FROM projects p ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
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
