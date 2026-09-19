"""Deterministic visual analysis (PRD §22), HEX extraction and the palette engine (PRD §23).

Pillow only, no network, no ML: same bytes in, same numbers out. Analysis runs on thumbnails at
download time and is stored on the asset - the database is the analysis cache (PRD §63).
Video motion (§22 motion_score) waits for M5, when FFmpeg can hand us real frames.
"""
import colorsys
import io
import statistics

from PIL import Image

SIZE = 100  # analysis resolution: small enough to be instant, large enough to be stable

STOPWORDS = {"a", "an", "the", "and", "or", "at", "of", "in", "on", "with", "over", "under", "by", "for", "to", "from"}
QUALITY_FLOOR = 0.45  # PRD §78: below this (near-black, blown, single-colour) an asset is not offered at all


def _hex(rgb: tuple) -> str:
    return "#%02X%02X%02X" % tuple(round(v) for v in rgb)


def _hex01(rgb: tuple) -> str:
    return _hex(tuple(v * 255 for v in rgb))


def _rgb(hex_str: str) -> tuple:
    return tuple(int(hex_str[i:i + 2], 16) / 255 for i in (1, 3, 5))


def analyze(data: bytes) -> dict:
    img = Image.open(io.BytesIO(data)).convert("RGB").resize((SIZE, SIZE), Image.NEAREST)
    px = list(img.getdata())
    luma = [(0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 for r, g, b in px]
    mean = statistics.fmean(luma)

    # gradient energy: per-pixel change, summed into left/center/right thirds (composition proxy)
    grad = 0.0
    cols = [0.0, 0.0, 0.0]
    for y in range(SIZE - 1):
        for x in range(SIZE - 1):
            i = y * SIZE + x
            d = abs(luma[i] - luma[i + 1]) + abs(luma[i] - luma[i + SIZE])
            grad += d
            cols[x * 3 // SIZE] += d
    subject = "center"
    if cols[0] > cols[1] and cols[0] >= cols[2]:
        subject = "left"
    elif cols[2] > cols[1] and cols[2] > cols[0]:
        subject = "right"

    return {
        "brightness": round(mean, 3),
        "contrast": round(min(statistics.pstdev(luma) / 0.3, 1.0), 3),
        "saturation": round(statistics.fmean((max(p) - min(p)) / max(max(p), 1) for p in px), 3),
        "temperature": "warm" if _warmth(px) > 0.04 else "cool" if _warmth(px) < -0.04 else "neutral",
        "dominant_colors": _dominant(img),
        "subject_position": subject,
        "visual_complexity": round(min(grad / ((SIZE - 1) ** 2) / 0.15, 1.0), 3),
    }


def _warmth(px) -> float:
    n = len(px)
    return (sum(p[0] for p in px) - sum(p[2] for p in px)) / (n * 255)


def _dominant(img: Image.Image) -> list[str]:
    """Up to 3 most frequent colours as HEX, near-duplicates merged (RGB distance > 60)."""
    q = img.quantize(colors=8)
    pal = q.getpalette()
    picked: list[tuple] = []
    for _, idx in sorted(q.getcolors(SIZE * SIZE), reverse=True):
        rgb = tuple(pal[idx * 3:idx * 3 + 3])
        if all(sum(abs(a - b) for a, b in zip(rgb, old)) > 60 for old in picked):
            picked.append(rgb)
        if len(picked) == 3:
            break
    return [_hex(c) for c in picked]


def no_neon(sat: float) -> float:
    """Brand constraint (PRD §24): restrained saturation scores full, neon decays to zero."""
    return 1.0 if sat <= 0.6 else max(0.0, 1 - (sat - 0.6) * 2.5)


def quality(a: dict) -> float:
    """Intrinsic technical quality (PRD §77/§78): exposure, real contrast, restrained saturation, colour richness."""
    exposure = max(0.0, 1 - abs(a["brightness"] - 0.5) * 2)
    contrast = min(a["contrast"] / 0.15, 1.0)
    richness = min(len(a["dominant_colors"]) / 3, 1.0)
    return round(0.4 * exposure + 0.2 * contrast + 0.2 * no_neon(a["saturation"]) + 0.2 * richness, 3)


def themes_from_query(query: str) -> list[str]:
    """Visual category keywords from the search that found the asset; feeds the category cooldown (PRD §18)."""
    words = [w for w in query.lower().split() if len(w) > 2 and w not in STOPWORDS]
    return list(dict.fromkeys(words))[:3]


def palette(dominant: list[str]) -> dict:
    """Source visual → accessible design tokens (PRD §23), clamped to the brand identity (§24): no neon."""
    cols = [colorsys.rgb_to_hls(*_rgb(h)) for h in dominant]  # (h, l, s)
    if not cols:
        cols = [colorsys.rgb_to_hls(0.12, 0.12, 0.12)]

    mids = [c for c in cols if 0.15 <= c[1] <= 0.75] or cols
    h, l, s = max(mids, key=lambda c: c[2])
    primary = colorsys.hls_to_rgb(h, min(max(l, 0.28), 0.6), min(s, 0.5))

    second = next((c for c in cols if abs(c[0] - h) > 60 / 360 and c[2] > 0.15), None)
    if second is None:
        second = ((h + 30 / 360) % 1, 0.62, 0.22)
    secondary = colorsys.hls_to_rgb(second[0], min(max(second[1], 0.5), 0.8), min(second[2], 0.3))

    darkest, lightest = min(cols, key=lambda c: c[1]), max(cols, key=lambda c: c[1])
    dark = colorsys.hls_to_rgb(darkest[0], 0.13, min(darkest[2], 0.3))
    light = colorsys.hls_to_rgb(lightest[0], 0.93, min(lightest[2], 0.2))

    pr, pg, pb = primary
    text = (1.0, 1.0, 1.0) if 0.2126 * pr + 0.7152 * pg + 0.0722 * pb < 0.45 else (0.09, 0.08, 0.06)

    return {"primary": _hex01(primary), "secondary": _hex01(secondary), "dark": _hex01(dark),
            "light": _hex01(light), "text": _hex01(text), "overlay": _hex01(dark)}
