"""Swatches for the Create page: every still design and caption style drawn by the real renderers (PIL for the
stills, libass through ffmpeg for the captions), over the newest picture in the Library. Nothing here is a mock:
a swatch is exactly what a render with those choices produces, only smaller."""
import base64
import io
import tempfile
from pathlib import Path

from PIL import Image

from app import config, design, render, visual
from app.clipper.captions import CAPTION_FONTS, PRESETS, CaptionStyle, captions
from app.clipper.ff import ffmpeg
from app.database import connect

SAMPLE = {"text": "Your comfort zone will kill you.", "author": None}
SAMPLE_PALETTE = {"primary": "#8A5A2B", "secondary": "#A89070", "dark": "#1E1611", "light": "#F1ECE4",
                  "text": "#FFFFFF", "overlay": "#1E1611"}
STYLE_LABELS = {"karaoke": "Karaoke", "pop": "Word pop", "clean": "Clean", "boxed": "Boxed", "minimal": "Minimal",
                "serif": "Serif", "marker": "Marker", "duet": "Duet"}


def _backdrop() -> Image.Image | None:
    """The newest Library picture (a video's thumbnail stands in for its frames); None on a fresh install."""
    with connect() as conn:
        rows = conn.execute("SELECT asset_type, local_path, thumb_path FROM assets ORDER BY rowid DESC LIMIT 6").fetchall()
    for r in rows:
        for rel in ((r["local_path"],) if r["asset_type"] == "image" else ()) + (r["thumb_path"],):
            path = config.MEDIA_DIR / rel if rel else None
            if path and path.is_file():
                try:
                    img = Image.open(path)
                    img.load()
                    return img.convert("RGB")
                except OSError:
                    continue
    return None


def _data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def designs(font: str = "auto", position: str = "auto", quote: dict | None = None, design_name: str = "auto",
            genre: str = "hope", quotes: list[str] | None = None, swatches: bool = True) -> dict:
    """Every design as a swatch, plus `samples`: the first pieces of the batch exactly as they will be designed
    (the user's own quotes when given, "auto" resolved per piece the way the render resolves it)."""
    from app.content import split_author
    photo = _backdrop()
    q = {**SAMPLE, **(quote or {})}
    out = [{"id": key, "label": label,
            "src": _data_url(design.compose(key, photo, q, SAMPLE_PALETTE, 432, 540, face=font, position=position))}
           for key, label in design.DESIGNS.items()] if swatches else []
    lines = [split_author(x) for x in (quotes or []) if x.strip()][:3]
    own = [{"text": t, "author": a} for t, a in lines] or [SAMPLE, {"text": "Life has no script. Live it."},
                                                           {"text": "Begin before you feel ready."}]
    samples = []
    for i, sq in enumerate(own):
        chosen = design.pick(design_name, genre, None, i, sq["text"])
        img = design.compose(chosen, photo, sq, SAMPLE_PALETTE, 648, 810, face=font, position=position)
        samples.append({"design": chosen, "label": design.DESIGNS[chosen], "src": _data_url(img)})
    return {"designs": out, "fonts": design.HEADLINE_FONTS, "samples": samples, "own": bool(lines),
            "photo": photo is not None, "palettes": {k: v["label"] for k, v in visual.PALETTES.items()}}


def caption_styles(style: dict | None = None) -> dict:
    """One swatch per caption style, each with the user's other choices (font, position, size, colour, case)."""
    base = CaptionStyle.model_validate(style or {}).model_dump()
    photo = _backdrop()
    w, h = 360, 640
    bg = design.cover(photo, w, h) if photo else Image.new("RGB", (w, h), SAMPLE_PALETTE["dark"])
    bg = design.grade(bg, 0.8)
    words = [{"word": t, "start": i * 0.4, "end": i * 0.4 + 0.38} for i, t in enumerate(SAMPLE["text"].split())]
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        bg.save(tmpd / "bg.jpg", quality=92)
        for key in PRESETS:
            ass = captions(words, 0, 3, w, h, ["comfort"], {**base, "style": key},
                           accent=design.accent(SAMPLE_PALETTE), plate=SAMPLE_PALETTE["dark"])
            (tmpd / f"{key}.ass").write_text(ass, encoding="utf-8")
            fonts = render.esc(str(design.FONTS_DIR).replace("\\", "/"))
            # frame at 0.62 s: the second word is lit and every entrance animation has finished
            ffmpeg("-loop", "1", "-i", "bg.jpg", "-vf", f"ass={key}.ass:fontsdir='{fonts}'", "-ss", "0.62",
                   "-frames:v", "1", f"{key}.jpg", cwd=tmpd, timeout=30)
            out.append({"id": key, "label": STYLE_LABELS[key], "src": _data_url(Image.open(tmpd / f"{key}.jpg"))})
    return {"styles": out, "fonts": CAPTION_FONTS}
