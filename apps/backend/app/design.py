"""Art-directed still designs (owner brief 2026-11-07: "think like a high end graphic designer").

Each design is a composition with its own type pairing, grade and texture, drawn with PIL. Rules every design keeps:
- one dominant line and one quiet one (real hierarchy), never two shouting voices;
- balanced rags: line breaks chosen for even line lengths and sentence ends, never a lone last word;
- secondary text in tracked capitals, small and quiet;
- every glyph inside the margins; text sized to fit, never cut off;
- soft (blurred) shadows only where a photo needs them; grain and vignette so nothing looks flat or synthetic.
Fonts are bundled (assets/fonts, all SIL OFL), so output is identical on every machine.
"""
import colorsys
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FACES = {
    "poster": "BigShoulders-Bold.ttf",          # condensed display capitals
    "heavy": "Boldonse-Regular.ttf",            # wide black display
    "grotesk": "BricolageGrotesque-Bold.ttf",
    "serif-display": "Gloock-Regular.ttf",      # high-contrast display serif
    "serif": "InstrumentSerif-Regular.ttf",
    "serif-italic": "InstrumentSerif-Italic.ttf",
    "sans": "InstrumentSans-Regular.ttf",
    "sans-bold": "InstrumentSans-Bold.ttf",
    "geometric": "Outfit-Bold.ttf",
    "montserrat": "Montserrat-ExtraBold.ttf",
    "label": "WorkSans-Regular.ttf",            # tracked small capitals
    "sora": "Sora-Variable.ttf",
}
# headline faces a user may force over a design's own pairing (Create > Image design > Headline font)
HEADLINE_FONTS = {"auto": "Matches the design", "poster": "Big Shoulders (condensed)", "heavy": "Boldonse (wide black)",
                  "montserrat": "Montserrat (bold geometric)", "geometric": "Outfit (clean geometric)",
                  "grotesk": "Bricolage (editorial grotesk)", "serif-display": "Gloock (display serif)",
                  "serif-italic": "Instrument Serif (italic)", "sans": "Instrument Sans (light touch)"}
# The 2026-11-13 set (owner replaced the original thirteen): every design stresses one beat word of the quote.
DESIGNS = {"arch": "Arch window", "verse": "Verse", "marker": "Marker word", "strips": "Torn strips",
           "velvet": "Velvet", "moon": "Moonlit", "stripes": "Stripes", "giant": "Giant word"}
GENRE_DESIGNS = {"hope": ["arch", "marker", "stripes", "verse", "moon", "strips"],
                 "speech": ["giant", "marker", "velvet", "stripes", "strips"],
                 "stoic": ["velvet", "verse", "arch", "giant", "moon"],
                 "history": ["arch", "velvet", "verse", "strips", "moon"],
                 "books": ["verse", "arch", "strips", "velvet", "stripes"],
                 "cinema": ["moon", "velvet", "giant", "marker", "strips"]}
COMPOSITION = {"minimal": "verse", "bold": "giant", "editorial": "strips", "centered": "velvet"}
SHORT_ONLY = {"giant": 30, "strips": 30, "marker": 34, "velvet": 34, "moon": 34, "stripes": 34}  # words: past this the design stops reading well
INK, BONE = "#151413", "#F3F0EA"


# ---------- choosing ----------

def pick(design: str, genre: str, composition: str | None, idx: int, text: str) -> str:
    """The user's choice wins; "auto" takes the genre's designs, honours the writer's composition hint when the
    genre allows it, and rotates by piece so a project reads as a series, not one template repeated."""
    if design in DESIGNS:
        return design
    words = len(text.split())
    options = [d for d in GENRE_DESIGNS.get(genre, GENRE_DESIGNS["hope"]) if words <= SHORT_ONLY.get(d, 99)]
    options = options or ["arch"]
    hinted = COMPOSITION.get(composition or "")
    if hinted in options and idx % 2 == 0:
        return hinted
    return options[idx % len(options)]


def another(current: str, genre: str, text: str) -> str:
    """The genre's next design after `current` that fits this quote's length: what "new design" means."""
    words = len(text.split())
    options = [d for d in GENRE_DESIGNS.get(genre, GENRE_DESIGNS["hope"]) if words <= SHORT_ONLY.get(d, 99)] or ["arch"]
    return options[(options.index(current) + 1) % len(options)] if current in options else options[0]


def copy_for(quote: dict) -> dict:
    """What a design sets: the quote and its author. Nothing is added around them (owner, 2026-11-08: no emphasis
    phrase, no kicker line; simple content reads better)."""
    return {"text": " ".join(quote["text"].split()), "author": (quote.get("author") or "").strip()}


def _norm(s: str) -> str:
    return re.sub(r"[^\w ]", "", s.lower())


# ---------- colour ----------

def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ra, rb))


def tone(h: str, light: float, max_sat: float = 0.55) -> str:
    hh, _, s = colorsys.rgb_to_hls(*(c / 255 for c in _rgb(h)))
    return "#" + "".join(f"{round(c * 255):02X}" for c in colorsys.hls_to_rgb(hh, light, min(s, max_sat)))


def accent(pal: dict) -> str:
    """The palette's primary lifted to read on dark ground, never neon (brand rule §24)."""
    return tone(pal.get("primary", "#B08A5A"), 0.70)


def rgba(h: str, a: int = 255) -> tuple[int, int, int, int]:
    return (*_rgb(h), a)


# ---------- photo treatment ----------

def cover(img: Image.Image, w: int, h: int, subject: str = "center", y_focus: float = 0.45) -> Image.Image:
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    rw, rh = max(w, round(img.width * s)), max(h, round(img.height * s))
    img = img.resize((rw, rh), Image.LANCZOS)
    x = {"left": 0, "right": rw - w}.get(subject, (rw - w) // 2)
    y = min(max(round((rh - h) * y_focus), 0), rh - h)
    return img.crop((x, y, x + w, y + h))


def grade(img: Image.Image, bright=1.0, contrast=1.0, color=1.0) -> Image.Image:
    img = ImageEnhance.Color(img).enhance(color)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    return ImageEnhance.Brightness(img).enhance(bright)


def vignette(img: Image.Image, strength: float, color: str = "#000000") -> Image.Image:
    w, h = img.size
    mask = Image.radial_gradient("L").resize((w, h), Image.BICUBIC)  # 0 centre -> 255 corners
    mask = mask.point(lambda v: max(0, min(255, round((v - 70) * 1.5 * strength))))
    return Image.composite(Image.new("RGB", (w, h), color), img.convert("RGB"), mask)


def gradient(w: int, h: int, color: str, stops: list[tuple[float, int]]) -> Image.Image:
    """Vertical RGBA gradient through (position 0..1, alpha) stops, eased so the fade has no visible edge."""
    col = Image.new("RGBA", (1, h))
    r, g, b = _rgb(color)
    px = []
    for y in range(h):
        t = y / max(h - 1, 1)
        a = stops[-1][1]
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / max(p1 - p0, 1e-6)
                k = k * k * (3 - 2 * k)  # smoothstep
                a = a0 + (a1 - a0) * k
                break
        else:
            a = stops[0][1] if t < stops[0][0] else stops[-1][1]
        px.append((r, g, b, round(a)))
    col.putdata(px)
    return col.resize((w, h))


def over(img: Image.Image, layer: Image.Image) -> Image.Image:
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def grain(img: Image.Image, amount: float) -> Image.Image:
    """Film grain: overlay-blended noise, finer than a pixel pattern and strongest in the mids."""
    noise = Image.effect_noise(img.size, 48).convert("RGB")
    return Image.blend(img, ImageChops.overlay(img, noise), amount)


def paper(w: int, h: int, base: str) -> Image.Image:
    """Crumpled paper: broad soft blotches, embossed creases and a fine tooth, overlaid on the base tone."""
    blotch = Image.effect_noise((max(2, w // 120), max(2, h // 120)), 50).resize((w, h), Image.BICUBIC)
    crease = Image.effect_noise((max(2, w // 26), max(2, h // 26)), 90).resize((w, h), Image.BICUBIC)
    crease = crease.filter(ImageFilter.EMBOSS).filter(ImageFilter.GaussianBlur(1.2))
    shade = ImageChops.add(blotch.point(lambda v: (v - 128) * 0.6 + 64), crease.point(lambda v: (v - 128) * 1.9 + 64))
    surface = ImageChops.overlay(Image.new("RGB", (w, h), base), shade.convert("RGB"))
    return grain(surface, 0.18)


# ---------- type ----------

@lru_cache(maxsize=512)
def font(face: str, size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS_DIR / FACES[face]), max(6, int(size)))
    if face == "sora":
        try:
            f.set_variation_by_axes([600])
        except OSError:
            pass
    return f


def tokens(text: str) -> list[tuple[str, bool]]:
    """Words as (word, stressed) pairs; the layout engine still honours the flag, which only Statement sets."""
    return [(w, False) for w in text.split()]


class Style:
    """How a run of text is set: faces (plain + emphasis), size, tracking (em), leading, case, colours."""

    def __init__(self, face, size, fill, *, emph_face=None, emph_fill=None, tracking=0.0, leading=1.2,
                 case=None, alpha=255):
        self.face, self.size, self.fill = face, round(size), fill
        self.emph_face, self.emph_fill = emph_face or face, emph_fill or fill
        self.tracking, self.leading, self.case, self.alpha = tracking, leading, case, alpha

    def f(self, emph=False):
        return font(self.emph_face if emph else self.face, self.size)

    def word(self, w: str) -> str:
        return w.upper() if self.case == "upper" else w.lower() if self.case == "lower" else w

    def width(self, w: str, emph=False) -> float:
        w = self.word(w)
        return self.f(emph).getlength(w) + self.tracking * self.size * max(len(w) - 1, 0)

    @property
    def space(self) -> float:
        return self.f().getlength(" ") + self.tracking * self.size

    @property
    def cap(self) -> int:
        box = self.f().getbbox("HXd", anchor="ls")
        return -box[1]


def breaks(toks, st: Style, max_w: float, max_lines: int = 99):
    """Every sentence starts a new line when the line budget allows (a designer never runs "you. stop" together);
    otherwise one balanced run."""
    sentences, cur = [], []
    for t in toks:
        cur.append(t)
        if t[0][-1] in ".!?":
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    if len(sentences) > 1:
        parts = [_breaks(sn, st, max_w, max_lines) for sn in sentences]
        if all(parts) and sum(len(p) for p in parts) <= max_lines:
            return [ln for p in parts for ln in p]
    return _breaks(toks, st, max_w, max_lines)


def _breaks(toks, st: Style, max_w: float, max_lines: int = 99):
    """Fewest lines that fit, then the most even rag: minimum squared slack, sentence ends rewarded, a lone
    last word punished. None when a word alone is wider than the measure or the line budget is blown."""
    widths = [st.width(w, e) for w, e in toks]
    if not widths or max(widths) > max_w:
        return None
    space, n = st.space, len(widths)
    count, cur = 1, 0.0
    for w in widths:
        nxt = w if cur == 0 else cur + space + w
        if nxt > max_w:
            count, cur = count + 1, w
        else:
            cur = nxt
    if count > max_lines:
        return None
    pre = [0.0]
    for w in widths:
        pre.append(pre[-1] + w)

    def span(i, j):
        return pre[j] - pre[i] + space * (j - i - 1)

    inf = float("inf")
    most = min(count + 1, max_lines, n)  # one extra line may land the breaks on sentence ends
    dp = [[inf] * (n + 1) for _ in range(most + 1)]
    back = [[0] * (n + 1) for _ in range(most + 1)]
    dp[0][0] = 0.0
    bonus = (max_w * 0.38) ** 2
    for k in range(1, most + 1):
        for j in range(k, n + 1):
            for i in range(k - 1, j):
                if dp[k - 1][i] == inf:
                    continue
                w = span(i, j)
                if w > max_w:
                    continue
                cost = dp[k - 1][i] + (max_w - w) ** 2
                if j < n and toks[j - 1][0][-1] in ".,;:!?":
                    cost -= bonus
                if j == n and j - i == 1 and n > 2:
                    cost += bonus * 2
                if cost < dp[k][j]:
                    dp[k][j], back[k][j] = cost, i
    use = most if most > count and dp[most][n] + (max_w * 0.25) ** 2 < dp[count][n] else count
    lines, j = [], n
    for k in range(use, 0, -1):
        i = back[k][j]
        lines.append(toks[i:j])
        j = i
    return lines[::-1]


def fit(toks, st_for, max_w, max_h, sizes, max_lines=99):
    """Largest size (from `sizes`, big to small) whose balanced block fits the measure and the height."""
    for s in sizes:
        st = st_for(s)
        lines = breaks(toks, st, max_w, max_lines)
        if lines and block_h(st, len(lines)) <= max_h:
            return st, lines
    st = st_for(sizes[-1])
    return st, breaks(toks, st, max_w) or [toks]


def sizes(hi: float, lo: float, step: float = 0.95) -> list[int]:
    out, s = [], hi
    while s > lo:
        out.append(round(s))
        s *= step
    return out + [round(lo)]


def block_h(st: Style, n: int) -> int:
    return round(st.cap + st.size * st.leading * (n - 1))


def line_w(st: Style, line) -> float:
    return sum(st.width(w, e) for w, e in line) + st.space * (len(line) - 1)


def draw_lines(layer: Image.Image, st: Style, lines, x: float, top: float, align: str = "center",
               measure: float | None = None, boxes: list | None = None) -> float:
    """Set lines on an RGBA layer from the cap top at `top`; returns the y just below the last baseline.
    `x` is the left edge (left), the centre (center) or the right edge (right). `boxes` collects
    (x0, x1, baseline) of every stressed word, for designs that lay something under it."""
    d = ImageDraw.Draw(layer)
    base = top + st.cap
    for line in lines:
        lw = line_w(st, line)
        cx = {"left": x, "center": x - lw / 2, "right": x - lw}[align]
        for i, (w, e) in enumerate(line):
            word, f = st.word(w), st.f(e)
            fill = rgba(st.emph_fill if e else st.fill, st.alpha)
            if e and boxes is not None:
                boxes.append((cx, cx + st.width(w, e), base))
            if st.tracking:
                for ch in word:
                    d.text((cx, base), ch, font=f, fill=fill, anchor="ls")
                    cx += f.getlength(ch) + st.tracking * st.size
                cx -= st.tracking * st.size
            else:
                d.text((cx, base), word, font=f, fill=fill, anchor="ls")
                cx += f.getlength(word)
            if i < len(line) - 1:
                cx += st.space
        base += st.size * st.leading
    return base - st.size * st.leading


def shadowed(img: Image.Image, layer: Image.Image, alpha: float, blur: float, color="#000000") -> Image.Image:
    """Composite a text layer over a soft blurred shadow of itself: legible on any photo, never a hard drop."""
    if alpha > 0:
        mask = layer.getchannel("A").point(lambda v: round(v * alpha)).filter(ImageFilter.GaussianBlur(blur))
        sh = Image.new("RGBA", layer.size, rgba(color, 0))
        sh.putalpha(mask)
        img = over(img, sh)
    return over(img, layer)


# ---------- designs ----------
# Every design: (photo or None, copy, palette, w, h, opts) -> RGB image. opts: face (headline override or None),
# position ("auto" | "top" | "center" | "bottom"), subject ("left" | "right" | "center").

def _place(position: str, default: str, h: int, bh: float, top=0.16, bottom=0.86) -> float:
    pos = default if position == "auto" else position
    return {"top": h * top, "bottom": h * bottom - bh}.get(pos, (h - bh) / 2)


def _seed(text: str) -> int:
    return sum(ord(ch) * (i + 1) for i, ch in enumerate(text)) % 9973


def _light(hexcol: str) -> float:
    return colorsys.rgb_to_hls(*(v / 255 for v in _rgb(hexcol)))[1]


# ---------- 2026-11-13 set: one stressed beat per quote ----------
# Researched against Pinterest's 2026 trend reports (Poetcore, Vamp Romantic, tactile/imperfect) and current quote
# edits: the hook is contrast inside the line itself, one word the eye lands on, never two shouting voices.

STOP = set("a an the and or but nor of to in on at for with without into onto from by as is are was were be been "
           "being am you your yours i me my mine we us our it its this that these those not no so than then there "
           "what who whom which when where why how will would shall should can could may might must do does did "
           "done have has had he she him her his they them their all any each every just only very more most such "
           "own same too also if else once up down out over under again about".split())


def beat(toks):
    """The quote's punchline word, stressed: the last content word of the line ("...you will find strength."),
    where a reader's eye and a narrator's voice both land."""
    words = [re.sub(r"[^\w']", "", w).lower() for w, _ in toks]
    i = next((k for k in range(len(toks) - 1, -1, -1) if len(words[k]) > 2 and words[k] not in STOP), len(toks) - 1)
    return [(t, k == i) for k, (t, _) in enumerate(toks)]


def deep(pal: dict) -> str:
    """The palette's primary pulled down to a rich ink that reads on cream."""
    return tone(pal.get("primary", "#8A4B2E"), 0.30, 0.6)


def vivid(pal: dict, light: float = 0.6) -> str:
    """The palette's hue at full voice: saturation lifted, never left muddy."""
    hh, _, ss = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(pal.get("primary", "#E0B030"))))
    return "#" + "".join(f"{round(v * 255):02X}" for v in colorsys.hls_to_rgb(hh, light, min(max(ss, 0.72), 0.78)))


def arch(photo, c, pal, w, h, o):
    """Poetcore: a cream page, the photograph in an arch-topped window, the line in a text serif below with its
    last word turned to italic in the palette's deep ink, a tracked name closing it."""
    u = w / 1080
    ground = mix("#F2ECE1", pal.get("light", "#EEE6D8"), 0.3)
    img = paper(w, h, ground)
    aw, ah = round(w * 0.56), round(h * 0.40)
    ax, ay = (w - aw) // 2, round(h * 0.075)
    pic = grade(cover(photo, aw, ah, o["subject"]), 1.02, 1.02, 0.9) if photo else Image.new("RGB", (aw, ah), pal["dark"])
    mask = Image.new("L", (aw * 3, ah * 3))
    md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, aw * 3, aw * 3), fill=255)
    md.rectangle((0, aw * 3 // 2, aw * 3, ah * 3), fill=255)
    mask = mask.resize((aw, ah), Image.LANCZOS)
    img.paste(pic, (ax, ay), mask)
    ink = deep(pal)
    line = ImageDraw.Draw(img)
    line.rectangle((ax, ay + ah + round(28 * u), ax + aw, ay + ah + round(28 * u) + max(1, round(1.5 * u))), fill=ink)

    toks = beat(tokens(c["text"]))
    area = ay + ah + 80 * u
    st, lines = fit(toks, lambda s: Style(o["face"] or "serif", s, "#1F1B17", emph_face="serif-italic", emph_fill=ink,
                                          leading=1.12), w * 0.80, h - area - 150 * u, sizes(92 * u, 40 * u), 6)
    lab = Style("label", 21 * u, "#5A534A", tracking=0.32, case="upper")
    gap = st.size * 0.7
    bh = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    top = area + max(0, (h - 90 * u - area - bh) / 2)
    layer = Image.new("RGBA", (w, h))
    y = draw_lines(layer, st, lines, w / 2, top)
    if c["author"]:
        draw_lines(layer, lab, [tokens(c["author"])], w / 2, y + gap)
    return over(img, layer)


def marker(photo, c, pal, w, h, o):
    """The photograph left bright, a bold sentence in white across its open sky or ground, and the punchline word
    knocked out of a solid block of the palette's colour: the one place the eye goes first."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"]) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = vignette(grade(base, 0.9, 1.06, 1.02), 0.35)
    pos = "bottom" if o["position"] == "auto" else o["position"]
    block = vivid(pal)  # the one vivid thing in the frame
    word_ink = INK if _light(block) > 0.5 else "#FFFFFF"
    toks = beat(tokens(c["text"]))
    face = o["face"] or "sans-bold"
    st, lines = fit(toks, lambda s: Style(face, s, "#FFFFFF", emph_fill=word_ink, leading=1.2),
                    w - 2 * 92 * u, h * 0.36, sizes(84 * u, 40 * u), 6)
    lab = Style("label", 22 * u, "#FFFFFF", tracking=0.3, case="upper", alpha=225)
    gap = st.size * 0.9
    bh = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    top = _place(pos, "bottom", h, bh, 0.12, 0.88)
    fade = {"bottom": [(max(0, top / h - 0.22), 0), (1, 175)], "top": [(0, 175), (min(1, (top + bh) / h + 0.22), 0)]}
    img = over(img, gradient(w, h, "#000000", fade.get(pos, [(0, 70), (1, 70)])))
    m = 92 * u
    boxes = []
    draw_lines(Image.new("RGBA", (w, h)), st, lines, m, top, "left", boxes=boxes)  # dry run: where the word lands
    layer = Image.new("RGBA", (w, h))
    pd, pad = ImageDraw.Draw(layer), st.space * 0.38
    for x0, x1, b in boxes:
        pd.rounded_rectangle((x0 - pad, b - st.cap - st.size * 0.14, x1 + pad, b + st.size * 0.2), radius=st.size * 0.1,
                             fill=rgba(block))
    y = draw_lines(layer, st, lines, m, top, "left")
    if c["author"]:
        draw_lines(layer, lab, [tokens(c["author"])], m, y + gap, "left")
    return shadowed(grain(img, 0.06), layer, 0.45, 14 * u)


def strips(photo, c, pal, w, h, o):
    """Collage: the line cut into torn strips of paper, one per line, each a little crooked, laid over the
    photograph with a soft contact shadow. The tactile, made-by-hand look of 2026 feeds."""
    import random
    u = w / 1080
    base = cover(photo, w, h, o["subject"]) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = grain(vignette(grade(base, 0.92, 1.04, 0.95), 0.4), 0.05)
    rnd = random.Random(_seed(c["text"]))
    st, lines = fit(beat(tokens(c["text"])), lambda s: Style(o["face"] or "serif", s, "#1A1714",
                                                              emph_face="serif-italic", emph_fill=deep(pal), leading=1.0),
                    w * 0.74, h * 0.5, sizes(78 * u, 38 * u), 7)
    stock = mix("#F4F0E6", pal.get("light", "#EEE8DC"), 0.25)
    pieces = []
    for ln in lines:
        lw = line_w(st, ln)
        px, py = st.size * 0.42, st.size * 0.30
        sw, sh = round(lw + 2 * px), round(st.cap + st.size * 0.28 + 2 * py)
        strip = Image.new("RGBA", (sw, sh))
        poly, n = [], 18
        poly += [(sw * k / n, rnd.uniform(0, py * 0.55)) for k in range(n + 1)]
        poly += [(sw - rnd.uniform(0, px * 0.25), sh * 0.5)]
        poly += [(sw * k / n, sh - rnd.uniform(0, py * 0.55)) for k in range(n, -1, -1)]
        poly += [(rnd.uniform(0, px * 0.25), sh * 0.5)]
        ImageDraw.Draw(strip).polygon(poly, fill=rgba(stock))
        draw_lines(strip, st, [ln], px, py, "left")
        pieces.append(strip.rotate(rnd.uniform(-1.8, 1.8), resample=Image.BICUBIC, expand=True))
    if c["author"]:  # the name on its own small strip, so it reads on any photo
        lab = Style("label", 20 * u, "#3A342E", tracking=0.3, case="upper")
        lw, px = line_w(lab, tokens(c["author"])), 26 * u
        tag = Image.new("RGBA", (round(lw + 2 * px), round(lab.cap + 34 * u)), rgba(stock))
        draw_lines(tag, lab, [tokens(c["author"])], px, 17 * u, "left")
        pieces.append(tag.rotate(rnd.uniform(-2.5, 2.5), resample=Image.BICUBIC, expand=True))
    step = [p.height - st.size * 0.08 for p in pieces]
    bh = sum(step)
    top = _place(o["position"], "center", h, bh, 0.12, 0.88)
    shadow, canvas = Image.new("RGBA", (w, h)), Image.new("RGBA", (w, h))
    y = top
    for p, s in zip(pieces, step):
        x = round((w - p.width) / 2 + rnd.uniform(-14, 14) * u)
        sh = Image.new("RGBA", p.size, (0, 0, 0, 0))
        sh.putalpha(p.getchannel("A").point(lambda v: round(v * 0.45)))
        shadow.alpha_composite(sh, (x + round(5 * u), round(y + 8 * u)))
        canvas.alpha_composite(p, (x, round(y)))
        y += s
    img = over(img, shadow.filter(ImageFilter.GaussianBlur(9 * u)))
    return over(img, canvas)


def velvet(photo, c, pal, w, h, o):
    """Vamp Romantic: the photograph toned into wine and plum, a display serif set large and centred low, its
    punchline in antique-gold italic between two gold hairlines. Dark, but rich colour, never grey."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"], 0.4) if photo else Image.new("RGB", (w, h), "#2A0F16")
    g = ImageEnhance.Contrast(ImageOps.grayscale(base)).enhance(1.15)
    img = ImageOps.colorize(g, black="#12060A", mid="#5E1A2A", white="#F1D9C6", blackpoint=6, whitepoint=252)
    img = Image.blend(img, grade(base, 1, 1, 0.6), 0.18)
    gold = "#D9B26A"
    pos = "bottom" if o["position"] == "auto" else o["position"]
    toks = beat(tokens(c["text"]))
    st, lines = fit(toks, lambda s: Style(o["face"] or "serif-display", s, "#F6EDE3", emph_face="serif-italic",
                                          emph_fill=gold, leading=1.08), w * 0.80, h * 0.38, sizes(96 * u, 42 * u), 6)
    lab = Style("label", 21 * u, gold, tracking=0.36, case="upper")
    rule = 46 * u
    bh = rule + block_h(st, len(lines)) + rule + (lab.cap + 30 * u if c["author"] else 0)
    top = _place(pos, "bottom", h, bh, 0.12, 0.88)
    fade = {"bottom": [(max(0, top / h - 0.25), 0), (1, 220)], "top": [(0, 220), (min(1, (top + bh) / h + 0.25), 0)]}
    img = over(img, gradient(w, h, "#12060A", fade.get(pos, [(0, 110), (1, 110)])))
    img = vignette(img, 0.7, "#0C0306")
    layer = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(layer)
    hair = max(1, round(1.5 * u))
    d.rectangle((w / 2 - 40 * u, top, w / 2 + 40 * u, top + hair), fill=rgba(gold))
    y = draw_lines(layer, st, lines, w / 2, top + rule)
    d.rectangle((w / 2 - 40 * u, y + rule * 0.7, w / 2 + 40 * u, y + rule * 0.7 + hair), fill=rgba(gold))
    if c["author"]:
        draw_lines(layer, lab, [tokens(c["author"])], w / 2, y + rule * 0.7 + 30 * u)
    return shadowed(grain(img, 0.07), layer, 0.5, 14 * u)


def verse(photo, c, pal, w, h, o):
    """Poetcore page: ivory paper, an oversized pale quotation mark, the line in a text serif flush left, its last
    word in italic with a fountain-pen stroke drawn under it. No photograph: the page is the image."""
    import math
    u = w / 1080
    img = paper(w, h, mix("#F5F0E6", pal.get("light", "#EEE6D8"), 0.2))
    ink, m = deep(pal), 118 * u
    st, lines = fit(beat(tokens(c["text"])), lambda s: Style(o["face"] or "serif", s, "#1F1B17", emph_face="serif-italic",
                                                              emph_fill=ink, leading=1.16), w - 2 * m, h * 0.5,
                    sizes(104 * u, 44 * u), 8)
    lab = Style("label", 21 * u, "#5A534A", tracking=0.32, case="upper")
    gap = st.size * 1.0
    bh = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    top = _place(o["position"], "center", h, bh, 0.24, 0.86) + h * 0.05
    layer, boxes = Image.new("RGBA", (w, h)), []
    d = ImageDraw.Draw(layer)
    d.text((m - 34 * u, top + 150 * u), "“", font=font("serif-display", round(520 * u)), fill=rgba(ink, 40),
           anchor="ls")
    y = draw_lines(layer, st, lines, m, top, "left", boxes=boxes)
    for x0, x1, b in boxes:  # a pen stroke: one gentle wave, thicker in the middle like a nib
        n, base_y = 48, b + st.size * 0.17
        pts = [(x0 - st.size * 0.05 + (x1 - x0 + st.size * 0.12) * k / n,
                base_y + math.sin(k / n * math.pi * 2.2) * st.size * 0.03 + k / n * st.size * 0.025) for k in range(n + 1)]
        for k in range(n):
            wid = max(2, round(st.size * (0.025 + 0.035 * math.sin(k / n * math.pi))))
            d.line(pts[k:k + 2], fill=rgba(ink, 235), width=wid)
    if c["author"]:
        draw_lines(layer, lab, [tokens("— " + c["author"])], m, y + gap, "left")
    return over(img, layer)


def stripes(photo, c, pal, w, h, o):
    """FunHaus: bold stripes in the palette's colour, a cream card with heavy capitals, the punchline in the stripe
    colour, the photograph as a round badge breaking the card's top edge. Loud, warm, made to be stopped at."""
    u = w / 1080
    col, cream = vivid(pal, 0.56), "#F7F0E3"
    img = Image.new("RGB", (w, h), cream)
    d = ImageDraw.Draw(img)
    sw = w / 9
    for k in range(0, 9, 2):
        d.rectangle((round(k * sw), 0, round((k + 1) * sw), h), fill=col)
    m, pad = 78 * u, 64 * u
    cw = w - 2 * m
    st, lines = fit(beat(tokens(c["text"])), lambda s: Style(o["face"] or "grotesk", s, INK, emph_fill=vivid(pal, 0.42),
                                                              leading=1.0, case="upper"), cw - 2 * pad, h * 0.46,
                    sizes(104 * u, 40 * u), 7)
    lab = Style("label", 21 * u, "#4A443D", tracking=0.32, case="upper")
    badge = round(w * 0.30) if photo else 0
    gap = st.size * 0.7
    tb = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    ch = tb + 2 * pad + badge * 0.55
    cy = _place(o["position"], "center", h, ch, 0.14, 0.9) + badge * 0.22
    card = Image.new("RGBA", (w, h))
    ImageDraw.Draw(card).rounded_rectangle((m, cy, m + cw, cy + ch), radius=46 * u, fill=rgba(cream))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh.putalpha(card.getchannel("A").point(lambda v: round(v * 0.35)))
    img = over(img, ImageChops.offset(sh, 0, round(14 * u)).filter(ImageFilter.GaussianBlur(20 * u)))
    img = over(img, card)
    if photo:
        rim = round(14 * u)
        disc = cover(photo, badge, badge, o["subject"])
        mask = Image.new("L", (badge * 3, badge * 3))
        ImageDraw.Draw(mask).ellipse((0, 0, badge * 3, badge * 3), fill=255)
        mask = mask.resize((badge, badge), Image.LANCZOS)
        bx, by = (w - badge) // 2, round(cy - badge * 0.45)
        ring = Image.new("L", (badge + 2 * rim, badge + 2 * rim))
        ImageDraw.Draw(ring).ellipse((0, 0, ring.width - 1, ring.height - 1), fill=255)
        img.paste(Image.new("RGB", ring.size, cream), (bx - rim, by - rim), ring.filter(ImageFilter.GaussianBlur(1)))
        img.paste(disc, (bx, by), mask)
    layer = Image.new("RGBA", (w, h))
    y = draw_lines(layer, st, lines, w / 2, cy + pad + badge * 0.55)
    if c["author"]:
        draw_lines(layer, lab, [tokens(c["author"])], w / 2, y + gap)
    return over(grain(img, 0.04), layer)


def moon(photo, c, pal, w, h, o):
    """Extra Celestial: the photograph toned to midnight blue, a pale moon rising behind it with a soft halo, the
    line in white serif beneath, its punchline in icy italic."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"], 0.6) if photo else Image.new("RGB", (w, h), "#0B1430")
    g = ImageEnhance.Contrast(ImageOps.grayscale(base)).enhance(1.1)
    img = ImageOps.colorize(g, black="#040816", mid="#1B2C58", white="#BFD6EE", blackpoint=4, whitepoint=255)
    img = ImageEnhance.Brightness(img).enhance(0.8)
    r, cx, cy = w * 0.17, w * 0.64, h * 0.20
    for spread, a in ((3.4, 110), (1.6, 190)):  # two halos: a wide bloom and a tighter glow
        halo = Image.new("L", (w, h))
        ImageDraw.Draw(halo).ellipse((cx - r * spread, cy - r * spread, cx + r * spread, cy + r * spread), fill=a)
        img = ImageChops.screen(img, Image.composite(Image.new("RGB", (w, h), "#7FA2D6"), Image.new("RGB", (w, h)),
                                                     halo.filter(ImageFilter.GaussianBlur(r * spread * 0.45))))
    d = round(2 * r)
    limb = Image.radial_gradient("L").resize((d, d), Image.BICUBIC).point(lambda v: 255 - max(0, v - 150) * 2)
    craters = Image.effect_noise((max(2, d // 18), max(2, d // 18)), 40).resize((d, d), Image.BICUBIC)
    surface = Image.new("RGB", (d, d), "#FBF8EF")
    surface = ImageChops.multiply(surface, craters.point(lambda v: 232 + v // 11).convert("RGB").filter(ImageFilter.GaussianBlur(d / 60)))
    surface = ImageChops.multiply(surface, Image.merge("RGB", (limb, limb, limb.point(lambda v: min(255, v + 12)))))
    mask = Image.new("L", (d * 3, d * 3))
    ImageDraw.Draw(mask).ellipse((0, 0, d * 3, d * 3), fill=255)
    img.paste(surface, (round(cx - r), round(cy - r)), mask.resize((d, d), Image.LANCZOS))
    st, lines = fit(beat(tokens(c["text"])), lambda s: Style(o["face"] or "serif-display", s, "#F4F7FA",
                                                              emph_face="serif-italic", emph_fill="#A8DBFF", leading=1.1),
                    w * 0.80, h * 0.34, sizes(90 * u, 40 * u), 6)
    lab = Style("label", 21 * u, "#A8C4E0", tracking=0.36, case="upper")
    gap = st.size * 0.8
    bh = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    lo = h * 0.5
    top = lo + max(0, (h * 0.93 - lo - bh) / 2) if o["position"] == "auto" else _place(o["position"], "bottom", h, bh)
    img = over(img, gradient(w, h, "#040816", [(max(0, top / h - 0.15), 0), (1, 200)]))
    layer = Image.new("RGBA", (w, h))
    y = draw_lines(layer, st, lines, w / 2, top)
    if c["author"]:
        draw_lines(layer, lab, [tokens(c["author"])], w / 2, y + gap)
    return shadowed(grain(img, 0.06), layer, 0.5, 14 * u)


def giant(photo, c, pal, w, h, o):
    """Oversized type: the punchline word set huge in the palette's vivid colour, cropped by the bottom edge, the
    whole line small and bright above it. The word is the poster; the sentence is the caption."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"], 0.35) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = over(grade(base, 0.86, 1.06, 0.95), gradient(w, h, "#000000", [(0.35, 0), (1, 210)]))
    toks = beat(tokens(c["text"]))
    word = re.sub(r"[^\w']", "", next(t for t, e in toks if e)).upper() or toks[-1][0].upper()
    gface = o["face"] or "montserrat"
    l, tp, rt, _ = font(gface, 100).getbbox(word, anchor="ls")
    size = min(100 * (w * 0.92) / max(rt - l, 1), 100 * (h * 0.30) / max(-tp, 1))
    gf = font(gface, round(size))
    l, tp, rt, _ = gf.getbbox(word, anchor="ls")
    base_y = h - tp * 0.05  # tp is negative: the baseline sits below the frame, so the letters run off it
    layer = Image.new("RGBA", (w, h))
    ImageDraw.Draw(layer).text(((w - (rt - l)) / 2 - l, base_y), word, font=gf, fill=rgba(vivid(pal, 0.58)), anchor="ls")
    m = 84 * u
    st, lines = fit([(t, False) for t, _ in toks], lambda s: Style("sans-bold", s, "#FFFFFF", leading=1.22),
                    w - 2 * m, h * 0.3, sizes(58 * u, 34 * u), 6)
    lab = Style("label", 21 * u, "#FFFFFF", tracking=0.3, case="upper", alpha=210)
    gap = st.size * 0.8
    bh = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    top = base_y + tp * 0.86 - 70 * u - bh
    text = Image.new("RGBA", (w, h))
    y = draw_lines(text, st, lines, m, top, "left")
    if c["author"]:
        draw_lines(text, lab, [tokens(c["author"])], m, y + gap, "left")
    return shadowed(over(grain(img, 0.06), layer), text, 0.55, 14 * u)


RENDER = {"arch": arch, "marker": marker, "strips": strips, "velvet": velvet, "verse": verse, "stripes": stripes,
          "moon": moon, "giant": giant}


def compose(design: str, photo: Image.Image | None, quote: dict, palette: dict, w: int, h: int, *,
            subject: str = "center", face: str = "auto", position: str = "auto") -> Image.Image:
    opts = {"face": face if face in FACES and face != "auto" else None, "position": position, "subject": subject}
    # a project saved before the 2026-11-13 set may still name a retired design
    return RENDER.get(design, arch)(photo, copy_for(quote), palette, w, h, opts)
