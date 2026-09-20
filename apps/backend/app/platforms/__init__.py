"""Platform metadata adapters (PRD §69-73). They shape one piece metadata set per platform and never publish."""
from app.errors import UserError

IG_CAPTION_MAX = 2200  # instagram + tiktok share the caption limit


def _tags(meta: dict) -> str:
    return " ".join(f"#{t.lstrip('#')}" for t in meta["hashtags"])


def _platform(files: dict, want: str) -> str:
    """The file's name inside the export folder; its presence is what the platform needs."""
    if want not in files:
        raise UserError("This piece has no render for what this platform needs.",
                        f"{want} missing; rendered: {', '.join(sorted(files)) or 'nothing'}")
    return want


def youtube_shorts(meta: dict, files: dict) -> dict:
    """PRD 70: title (<=100 chars), description carrying the hashtags, keywords."""
    return {"title": meta["title"][:100], "description": f'{meta["description"]}\n\n{_tags(meta)}',
            "keywords": meta["keywords"], "file": _platform(files, "video_9x16.mp4"), "cover": "thumbnail.jpg",
            "suggested_time": "17:00"}


def instagram(meta: dict, files: dict, want: str) -> dict:
    """PRD 71/72: reels take the 9:16 video, feed takes the 4:5 image; caption + hashtags within 2200 chars."""
    return {"caption": f'{meta["caption"]}\n\n{_tags(meta)}'[:IG_CAPTION_MAX],
            "hashtags": [f"#{t.lstrip('#')}" for t in meta["hashtags"]], "alt_text": meta["alt_text"],
            "file": _platform(files, want), "cover": "thumbnail.jpg", "suggested_time": "11:00"}


def tiktok(meta: dict, files: dict) -> dict:
    """PRD 73: caption with inline hashtags, 9:16 video, cover frame."""
    return {"caption": f'{meta["caption"]} {_tags(meta)}'[:IG_CAPTION_MAX], "file": _platform(files, "video_9x16.mp4"),
            "cover": "thumbnail.jpg", "suggested_time": "19:00"}


ADAPTERS = {"youtube_shorts": youtube_shorts, "instagram_reels": lambda m, f: instagram(m, f, "video_9x16.mp4"),
            "instagram_feed": lambda m, f: instagram(m, f, "image_4x5.jpg"), "tiktok": tiktok}


def adapt(platform: str, meta: dict, files: dict) -> dict:
    if platform not in ADAPTERS:
        raise UserError("That platform is not supported yet.", platform)
    return ADAPTERS[platform](meta, files)
