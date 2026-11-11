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
DESIGNS = {"noir": "Noir poster", "paper": "Paper note", "whisper": "Whisper", "statement": "Statement",
           "classic": "Classic serif", "split": "Editorial split", "stack": "Fitted stack", "notes": "Notes page",
           "highlight": "Book highlight", "riso": "Riso print", "subtitle": "Film subtitle", "polaroid": "Instant print",
           "swiss": "Swiss grid"}
GENRE_DESIGNS = {"hope": ["whisper", "notes", "polaroid", "paper", "riso", "classic"],
                 "speech": ["noir", "swiss", "stack", "subtitle", "paper"],
                 "stoic": ["classic", "highlight", "statement", "swiss", "noir"],
                 "history": ["classic", "highlight", "polaroid", "split", "noir"],
                 "books": ["highlight", "classic", "notes", "paper", "split"],
                 "cinema": ["subtitle", "whisper", "riso", "polaroid", "noir", "split"]}
COMPOSITION = {"minimal": "whisper", "bold": "stack", "editorial": "split", "centered": "classic"}
SHORT_ONLY = {"statement": 12, "stack": 14, "whisper": 20, "swiss": 16, "subtitle": 30, "riso": 22, "polaroid": 40}  # words: past this the design stops reading well
INK, BONE = "#151413", "#F3F0EA"


# ---------- choosing ----------

def pick(design: str, genre: str, composition: str | None, idx: int, text: str) -> str:
    """The user's choice wins; "auto" takes the genre's designs, honours the writer's composition hint when the
    genre allows it, and rotates by piece so a project reads as a series, not one template repeated."""
    if design in DESIGNS:
        return design
    words = len(text.split())
    options = [d for d in GENRE_DESIGNS.get(genre, GENRE_DESIGNS["hope"]) if words <= SHORT_ONLY.get(d, 99)]
    options = options or ["classic"]
    hinted = COMPOSITION.get(composition or "")
    if hinted in options and idx % 2 == 0:
        return hinted
    return options[idx % len(options)]


def another(current: str, genre: str, text: str) -> str:
    """The genre's next design after `current` that fits this quote's length: what "new design" means."""
    words = len(text.split())
    options = [d for d in GENRE_DESIGNS.get(genre, GENRE_DESIGNS["hope"]) if words <= SHORT_ONLY.get(d, 99)] or ["classic"]
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
               measure: float | None = None) -> float:
    """Set lines on an RGBA layer from the cap top at `top`; returns the y just below the last baseline.
    `x` is the left edge (left), the centre (center) or the right edge (right)."""
    d = ImageDraw.Draw(layer)
    base = top + st.cap
    for line in lines:
        lw = line_w(st, line)
        cx = {"left": x, "center": x - lw / 2, "right": x - lw}[align]
        for i, (w, e) in enumerate(line):
            word, f = st.word(w), st.f(e)
            fill = rgba(st.emph_fill if e else st.fill, st.alpha)
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


def label_lines(text: str) -> list[str]:
    """A tracked label breaks at its sentences ("STOP WAITING." / "START DOING.")."""
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


def sub_line(c: dict) -> str:
    return f"— {c['author']}" if c["author"] else ""


# ---------- designs ----------
# Every design: (photo or None, copy, palette, w, h, opts) -> RGB image. opts: face (headline override or None),
# position ("auto" | "top" | "center" | "bottom"), subject ("left" | "right" | "center").

def _place(position: str, default: str, h: int, bh: float, top=0.16, bottom=0.86) -> float:
    pos = default if position == "auto" else position
    return {"top": h * top, "bottom": h * bottom - bh}.get(pos, (h - bh) / 2)


def noir(photo, c, pal, w, h, o):
    """Monochrome cinema still, condensed capitals in the dark above the subject, a tracked whisper below."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"], 0.55) if photo else Image.new("RGB", (w, h), pal["dark"])
    g = ImageEnhance.Contrast(ImageOps.grayscale(base)).enhance(1.22)
    img = ImageOps.colorize(g, black=mix(pal["dark"], "#000000", 0.82), white="#EDEBE6", blackpoint=8,
                            whitepoint=250)
    img = ImageEnhance.Brightness(img).enhance(0.70)
    pos = "top" if o["position"] == "auto" else o["position"]

    text, sub = c["text"], sub_line(c)
    if not sub:  # "YOUR ONLY LIMIT IS YOU." / "STOP WAITING. START DOING."
        parts = re.split(r"(?<=[.!?])\s+", text)
        if len(parts) >= 2 and len(" ".join(parts[1:]).split()) <= 5:
            text, sub = parts[0], " ".join(parts[1:])
    head, lines = fit(tokens(text), lambda s: Style(o["face"] or "poster", s, "#F4F2EE", leading=0.94,
                                                    tracking=0.005, case="upper"),
                      w - 2 * 180 * u, h * 0.40, sizes(156 * u, 58 * u), 5)
    kick = Style("label", 27 * u, "#FFFFFF", tracking=0.40, leading=1.9, case="upper", alpha=215)
    kicks = [tokens(t) for t in label_lines(sub)] if sub else []
    gap = head.size * 0.62
    bh = block_h(head, len(lines)) + (gap + block_h(kick, len(kicks)) if kicks else 0)
    top = _place(pos, "top", h, bh, 0.15, 0.84)

    fade = {"top": [(0, 215), (min(1, (top + bh) / h + 0.18), 0)],
            "bottom": [(max(0, top / h - 0.18), 0), (1, 225)]}.get(pos, [(0, 90), (1, 90)])
    img = over(img, gradient(w, h, "#000000", fade))
    img = vignette(img, 0.9)
    layer = Image.new("RGBA", (w, h))
    y = draw_lines(layer, head, lines, w / 2, top)
    if kicks:
        draw_lines(layer, kick, kicks, w / 2, y + gap)
    return shadowed(grain(img, 0.10), layer, 0.55, 22 * u)


def paper_note(photo, c, pal, w, h, o):
    """A note on crumpled paper: heavy lowercase in a narrow column, printed into the sheet, a small sign-off."""
    u = w / 1080
    img = paper(w, h, mix("#E8E6E1", pal.get("light", "#EEEAE4"), 0.25))
    case = None if c["author"] else "lower"
    st, lines = fit(tokens(c["text"]), lambda s: Style(o["face"] or "montserrat", s, INK, leading=0.98, case=case),
                    w * 0.62, h * 0.56, sizes(138 * u, 50 * u), 7)
    sign = sub_line(c)
    sign_st = Style("label", 22 * u, "#2A2826", tracking=0.14, case="upper")
    bw = max(line_w(st, ln) for ln in lines)
    gap = st.size * 0.42
    bh = block_h(st, len(lines)) + (gap + sign_st.cap if sign else 0)
    top = _place(o["position"], "center", h, bh) - h * 0.02
    x = (w - bw) / 2
    layer = Image.new("RGBA", (w, h))
    y = draw_lines(layer, st, lines, x, top, "left")
    if sign:
        draw_lines(layer, sign_st, [tokens(sign.replace("— ", "—"))], x, y + gap, "left")
    ink = Image.new("RGB", (w, h), "#FFFFFF")
    ink.paste(layer, (0, 0), layer)
    return ImageChops.multiply(img, ink.filter(ImageFilter.GaussianBlur(0.6)))  # printed into the fibres


def whisper(photo, c, pal, w, h, o):
    """A quiet scene and one small line in its negative space; the turn of the line set in bold."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"]) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = vignette(grade(base, 0.70, 1.05, 0.80), 0.5)
    face = o["face"] or "sans"
    st, lines = fit(tokens(c["text"]),
                    lambda s: Style(face, s, "#FFFFFF", emph_face="sans-bold" if face == "sans" else face,
                                    leading=1.38), w * 0.80, h * 0.3, [round(50 * u), round(44 * u), round(38 * u)], 4)
    sig = Style("label", 21 * u, "#FFFFFF", tracking=0.3, case="upper", alpha=170)
    gap = st.size * 1.1
    bh = block_h(st, len(lines)) + (gap + sig.cap if c["author"] else 0)
    top = _place(o["position"], "center", h, bh, 0.2, 0.8) - h * 0.04
    layer = Image.new("RGBA", (w, h))
    y = draw_lines(layer, st, lines, w / 2, top)
    if c["author"]:
        draw_lines(layer, sig, [tokens(c["author"])], w / 2, y + gap)
    return shadowed(grain(img, 0.08), layer, 0.6, 16 * u)


def statement(photo, c, pal, w, h, o):
    """Swiss poster on a pale ground: a heavy quote mark, the one word that matters set huge, the rest small
    around it in reading order, and the photograph rising out of the ground below."""
    u = w / 1080
    ground = mix(pal.get("light", "#E6E6E4"), "#D8D8D6", 0.75)
    img = Image.new("RGB", (w, h), ground)
    if photo:
        ph = round(h * 0.54)
        pic = ImageOps.grayscale(cover(photo, w, ph, o["subject"], 0.6)).convert("RGB")
        pic = grade(pic, 0.98, 1.12)
        pic = ImageChops.multiply(pic, Image.new("RGB", (w, ph), mix(ground, "#FFFFFF", 0.35)))
        mask = gradient(w, ph, "#000000", [(0, 0), (0.42, 255), (1, 255)]).getchannel("A")
        img.paste(pic, (0, h - ph), mask)
    else:
        img.paste(mix(ground, "#FFFFFF", 0.45), (0, round(h * 0.80), w, h))

    toks = tokens(c["text"])
    if not any(e for _, e in toks):  # the longest word carries the poster
        i = max(range(len(toks)), key=lambda k: len(re.sub(r"\W", "", toks[k][0])))
        toks[i] = (toks[i][0], True)
    first = next(i for i, (_, e) in enumerate(toks) if e)
    last = max(i for i, (_, e) in enumerate(toks) if e)
    pre, big, post = toks[:first], [(t, False) for t, _ in toks[first:last + 1]], toks[last + 1:]

    measure = w * 0.76
    def big_st(s):
        st = Style(o["face"] or "heavy", s, INK, case="upper")
        st.leading = st.cap / st.size + 0.16  # heavy display caps run taller than the em: lead from the cap
        return st
    bst, blines = fit(big, big_st, measure, h * 0.22, sizes(176 * u, 84 * u), 1)
    if len(blines) > 1 or line_w(bst, blines[0]) > measure:
        bst, blines = fit(big, big_st, measure, h * 0.24, sizes(150 * u, 48 * u), 2)
    small = Style("sans-bold", max(30 * u, bst.size * 0.30), "#1C1B1A", tracking=0.08, leading=1.35, case="upper")
    bw = max(line_w(bst, ln) for ln in blines)
    plines = breaks(pre, small, max(bw, w * 0.5)) or [] if pre else []
    qlines = breaks(post, small, max(bw, w * 0.5)) or [] if post else []
    bw = max([bw] + [line_w(small, ln) for ln in plines + qlines])
    mark = Style("serif-display", max(bst.size * 1.4, 120 * u), INK, leading=1.0)
    gap = small.size * 0.55
    parts = [(mark, [[("”", False)]], bst.size * 0.05)] + [(small, plines, gap)] * bool(plines) + \
            [(bst, blines, gap)] + [(small, qlines, 0)] * bool(qlines)
    if sub := sub_line(c):  # the name closes the poster, small and tracked under the type
        lab = Style("label", max(24 * u, small.size * 0.8), "#1C1B1A", tracking=0.30, leading=1.6, case="upper")
        s, ls, _ = parts[-1]
        parts[-1] = (s, ls, gap * 1.6)
        parts.append((lab, [tokens(sub)], 0))
    bh = sum(block_h(s, len(ls)) + g for s, ls, g in parts)
    top = max(h * 0.09, min(h * 0.44 - bh, h * 0.14)) if o["position"] == "auto" else _place(o["position"], "top", h, bh, 0.1, 0.9)
    x = (w - bw) / 2
    layer = Image.new("RGBA", (w, h))
    y = top
    for s, ls, g in parts:
        y = draw_lines(layer, s, ls, x, y, "left") + g + s.size * 0.18
    return over(grain(img, 0.05), layer)


def classic(photo, c, pal, w, h, o):
    """Candlelit and quiet: an italic serif quotation, a hanging mark in the accent, a hairline and the name."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"]) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = grade(base, 0.44, 1.04, 0.55)
    img = Image.blend(img, Image.new("RGB", (w, h), pal["dark"]), 0.22)
    img = vignette(img, 0.85)
    acc = accent(pal)
    st, lines = fit(tokens(c["text"]), lambda s: Style(o["face"] or "serif-italic", s,
                                                       mix(BONE, pal.get("light", BONE), 0.3), leading=1.16),
                    w * 0.74, h * 0.48, sizes(92 * u, 42 * u), 8)
    mark = Style("serif-display", 150 * u, acc, alpha=210)
    name = sub_line(c).replace("— ", "")
    name_st = Style("label", 23 * u, "#FFFFFF", tracking=0.34, case="upper", alpha=205)
    gap = st.size * 0.75
    bh = mark.cap * 0.55 + gap + block_h(st, len(lines)) + (gap * 1.4 + name_st.cap if name else 0)
    top = _place(o["position"], "center", h, bh)
    layer = Image.new("RGBA", (w, h))
    draw_lines(layer, mark, [[("“", False)]], w / 2, top - mark.cap * 0.45)
    y = draw_lines(layer, st, lines, w / 2, top + mark.cap * 0.55 + gap)
    if name:
        d = ImageDraw.Draw(layer)
        ry = y + gap * 0.7
        d.rectangle((w / 2 - 34 * u, ry, w / 2 + 34 * u, ry + max(1, 2 * u)), fill=rgba(acc, 220))
        draw_lines(layer, name_st, [tokens(name)], w / 2, ry + gap * 0.7)
    return shadowed(grain(img, 0.08), layer, 0.5, 18 * u)


def split(photo, c, pal, w, h, o):
    """Magazine page: the photograph above, a solid panel in the palette's dark below, a tracked line in the
    accent and the line set in an editorial grotesk, ranged left on a margin."""
    u = w / 1080
    ph = round(h * 0.58)
    panel = tone(pal.get("dark", "#1A1714"), 0.11, 0.25)
    img = Image.new("RGB", (w, h), panel)
    if photo:
        img.paste(grade(cover(photo, w, ph, o["subject"]), 0.96, 1.06, 0.92), (0, 0))
    acc, m = accent(pal), 88 * u
    kick = sub_line(c).replace("— ", "")
    kst = Style("label", 25 * u, acc, tracking=0.3, case="upper")
    room = h - ph - 2 * m - (kst.cap + 34 * u if kick else 0)
    st, lines = fit(tokens(c["text"]), lambda s: Style(o["face"] or "grotesk", s, BONE, leading=1.08),
                    w - 2 * m, room, sizes(84 * u, 36 * u), 6)
    bh = block_h(st, len(lines)) + (kst.cap + 34 * u if kick else 0)
    top = ph + (h - ph - bh) / 2
    layer = Image.new("RGBA", (w, h))
    ImageDraw.Draw(layer).rectangle((m, ph - 3 * u, m + 96 * u, ph + 3 * u), fill=rgba(acc))
    y = top
    if kick:
        draw_lines(layer, kst, [tokens(kick)], m, y, "left")
        y += kst.cap + 34 * u
    draw_lines(layer, st, lines, m, y, "left")
    return over(grain(img, 0.06), layer)


def stack(photo, c, pal, w, h, o):
    """Fitted type: each line of condensed capitals scaled to the full measure, a solid wall of words over a
    dark scene."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"]) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = vignette(grade(base, 0.40, 1.12, 0.6), 0.7)
    face, acc, m = o["face"] or "poster", accent(pal), 84 * u
    measure, gap = w - 2 * m, 16 * u
    toks = tokens(c["text"])

    def lay(n):
        ref = Style(face, 100, BONE, case="upper")
        lines = breaks(toks, ref, line_w(ref, toks) / n * 1.18 + 1)
        out = []
        for ln in lines or [toks]:
            text = " ".join(ref.word(t) for t, _ in ln)
            box = font(face, 100).getbbox(text, anchor="ls")
            s = min(100 * measure / (box[2] - box[0]), 300 * u)
            out.append((ln, s))
        height = sum(-font(face, round(s)).getbbox(" ".join(t.upper() for t, _ in ln), anchor="ls")[1]
                     for ln, s in out) + gap * (len(out) - 1)
        return out, height

    best = None
    for n in range(1, min(len(toks), 7) + 1):
        out, height = lay(n)
        if height <= h * 0.74 and (best is None or abs(height - h * 0.58) < abs(best[1] - h * 0.58)):
            best = (out, height)
    out, height = best or lay(min(len(toks), 7))
    sub = sub_line(c)
    lab = Style("label", 28 * u, BONE, tracking=0.40, leading=1.6, case="upper", alpha=225)
    lab_gap = 44 * u
    top = _place(o["position"], "center", h, height + (lab_gap + block_h(lab, 1) if sub else 0), 0.14, 0.88)
    layer = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(layer)
    y = top
    for ln, s in out:
        text = " ".join(t.upper() for t, _ in ln)
        f = font(face, round(s))
        box = f.getbbox(text, anchor="ls")
        x = (w - (box[2] - box[0])) / 2 - box[0]
        y += -box[1]
        d.text((x, y), text, font=f, fill=rgba(acc if any(e for _, e in ln) else BONE), anchor="ls")
        y += gap
    if sub:  # the name sits under the wall, small and tracked so the wall stays the picture
        draw_lines(layer, lab, [tokens(sub)], w / 2, y - gap + lab_gap)
    return shadowed(grain(img, 0.08), layer, 0.45, 20 * u)



# ---------- designs added 2026-11-08 (owner: "more backgrounds, unique and in vogue") ----------
# Researched against 2026 feeds: tactile, made-by-hand surfaces (grain, paper, risograph, halftone, instant film) as a
# reaction to the flat AI look, plus formats that read as candid rather than designed (a note, a highlighted page).
# None imitates a real app's interface: no status bars, logos or brand chrome.

def _seed(text: str) -> int:
    return sum(ord(ch) * (i + 1) for i, ch in enumerate(text)) % 9973


def _light(hexcol: str) -> float:
    return colorsys.rgb_to_hls(*(v / 255 for v in _rgb(hexcol)))[1]


def notes(photo, c, pal, w, h, o):
    """A plain note: warm white page, the first sentence as a bold title, the rest as body text, flush left.
    Reads as written, not designed, which is the point of the format."""
    u = w / 1080
    img = grain(Image.new("RGB", (w, h), "#FBFAF6"), 0.025)
    m = 104 * u
    parts = re.split(r"(?<=[.!?])\s+", c["text"])
    title, body = (parts[0], " ".join(parts[1:])) if len(parts) > 1 and len(parts[0].split()) <= 14 else (c["text"], "")
    head, hlines = fit(tokens(title), lambda s: Style(o["face"] or "sans-bold", s, "#1C1B1A", leading=1.14),
                       w - 2 * m, h * (0.34 if body else 0.6), sizes(92 * u, 46 * u), 6)
    bst, blines = (fit(tokens(body), lambda s: Style("sans", s, "#34322F", leading=1.42), w - 2 * m, h * 0.36,
                       sizes(52 * u, 34 * u), 9) if body else (None, []))
    lab = Style("label", 21 * u, "#9A958E", tracking=0.16, case="upper")
    sign = c["author"] and f"— {c['author']}"
    gap = head.size * 0.7
    bh = block_h(head, len(hlines)) + (gap + block_h(bst, len(blines)) if bst else 0)
    top = h * 0.22 if o["position"] == "auto" else _place(o["position"], "top", h, bh)
    layer = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(layer)
    acc = mix(tone(pal.get("primary", "#E0A82E"), 0.6, 0.75), "#E9B530", 0.55)
    d.rounded_rectangle((m, top - 92 * u, m + 64 * u, top - 84 * u), radius=4 * u, fill=rgba(acc))
    y = draw_lines(layer, head, hlines, m, top, "left")
    if bst:
        y = draw_lines(layer, bst, blines, m, y + gap, "left")
    if sign:
        draw_lines(layer, lab, [tokens(sign)], m, y + head.size * 0.9, "left")
    return over(img, layer)


def highlight(photo, c, pal, w, h, o):
    """A page from a book: running head, the quote set in a text serif with a marker highlight laid down line by
    line, the rest of the page as faint lines of type, a folio at the foot."""
    import random
    u = w / 1080
    img = paper(w, h, "#F0E9DA")
    m = 118 * u
    st, lines = fit(tokens(c["text"]), lambda s: Style(o["face"] or "serif", s, "#221F1B", leading=1.52),
                    w - 2 * m, h * 0.44, sizes(72 * u, 40 * u), 9)
    lh = st.size * st.leading
    bh = block_h(st, len(lines))
    top = _place(o["position"], "center", h, bh, 0.2, 0.8)
    rnd = random.Random(_seed(c["text"]))
    marks = Image.new("RGBA", (w, h))
    md = ImageDraw.Draw(marks)
    yellow = mix("#F7DF4F", tone(pal.get("primary", "#F7DF4F"), 0.62, 0.8), 0.18)
    for i, line in enumerate(lines):  # the marker: a little long or short at each end, never a perfect box
        y0 = top + i * lh - st.size * 0.16
        md.rounded_rectangle((m - rnd.uniform(4, 14) * u, y0 + rnd.uniform(-3, 3) * u,
                              m + line_w(st, line) + rnd.uniform(4, 18) * u, y0 + st.cap + st.size * 0.34),
                             radius=6 * u, fill=rgba(yellow, 175))
    ghost = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(ghost)
    gl, gh = st.size * 0.95, max(5 * u, st.size * 0.14)
    for start, end in ((168 * u, top - lh * 0.9), (top + bh + lh * 0.9, h - 170 * u)):
        y, n = start, 0
        while y + gh < end:  # paragraphs of faint type around the passage; a short line ends each paragraph
            n += 1
            short = n % rnd.randint(4, 6) == 0
            gd.rounded_rectangle((m, y, m + (w - 2 * m) * (rnd.uniform(0.3, 0.6) if short else rnd.uniform(0.9, 1.0)), y + gh),
                                 radius=gh / 2, fill=rgba("#221F1B", 30))
            y += gl
    head_lab = Style("label", 19 * u, "#6E675D", tracking=0.22, case="upper")
    layer = Image.new("RGBA", (w, h))
    if c["author"]:
        draw_lines(layer, head_lab, [tokens(c["author"])], w / 2, 96 * u)
    draw_lines(layer, head_lab, [tokens(str(17 + _seed(c["text"]) % 260))], w / 2, h - 96 * u)
    draw_lines(layer, st, lines, m, top, "left")
    flat = Image.new("RGB", (w, h), "#FFFFFF")
    for lay in (ghost, marks, layer):  # every mark is ink on paper: multiplied into the sheet, not pasted on it
        tmp = Image.new("RGB", (w, h), "#FFFFFF")
        tmp.paste(lay, (0, 0), lay)
        flat = ImageChops.multiply(flat, tmp)
    return ImageChops.multiply(img, flat.filter(ImageFilter.GaussianBlur(0.5)))


def riso(photo, c, pal, w, h, o):
    """Two-colour risograph print: the photograph as fluorescent halftone dots, the words in the second ink with a
    slightly missed registration, both multiplied into uncoated paper."""
    u = w / 1080
    img = paper(w, h, "#F5F0E6")
    ink_a = "#FF5C9E"                                                     # fluorescent pink
    ink_b = mix("#1D46B5", tone(pal.get("primary", "#1D46B5"), 0.36, 0.8), 0.22)  # deep riso blue, palette-tinted
    if photo:
        g = ImageOps.autocontrast(ImageOps.grayscale(cover(photo, w, h, o["subject"])), cutoff=2)
        g = ImageEnhance.Brightness(g).enhance(1.3)  # riso halftones read light: paper must show between the dots
    else:
        g = ImageOps.invert(Image.radial_gradient("L").resize((w, h)))
    cell = max(6, round(13 * u))
    small = g.resize((w // cell + 2, h // cell + 2), Image.BILINEAR)
    dots = Image.new("L", (w, h), 0)
    dd = ImageDraw.Draw(dots)
    for j in range(small.height):
        for i in range(small.width):
            r = cell * 0.56 * ((255 - small.getpixel((i, j))) / 255) ** 1.5
            if r > 0.7:
                cx, cy = i * cell + (cell / 2 if j % 2 else 0), j * cell
                dd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=225)
    img = Image.composite(ImageChops.multiply(img, Image.new("RGB", (w, h), ink_a)), img, dots)
    m = 84 * u
    head, lines = fit(tokens(c["text"]),
                      lambda s: Style(o["face"] or "grotesk", s, "#000000", leading=0.98, case="upper"),
                      w - 2 * m, h * 0.42, sizes(132 * u, 52 * u), 6)
    sub = sub_line(c)
    lab = Style("label", 24 * u, "#000000", tracking=0.3, case="upper")
    gap = head.size * 0.5
    bh = block_h(head, len(lines)) + (gap + lab.cap if sub else 0)
    top = _place(o["position"], "bottom", h, bh, 0.12, 0.9)
    mask = Image.new("RGBA", (w, h))
    y = draw_lines(mask, head, lines, m, top, "left")
    small = Image.new("RGBA", (w, h))
    if sub:  # the small label prints in the blue drum only: misregistration would make it unreadable
        draw_lines(small, lab, [tokens(sub)], m, y + gap, "left")
    alpha = mask.getchannel("A")
    shift = round(7 * u)
    for ink, dx, dy, k in ((ink_a, shift, round(5 * u), 0.55), (ink_b, 0, 0, 0.92)):  # pink drum first, off by a hair
        a = ImageChops.offset(alpha, dx, dy).point(lambda v: round(v * k))
        if ink == ink_b:
            a = ImageChops.lighter(a, small.getchannel("A"))
        img = Image.composite(ImageChops.multiply(img, Image.new("RGB", (w, h), ink)), img, a)
    return grain(img, 0.06)


def subtitle(photo, c, pal, w, h, o):
    """A frame from a film: split-toned grade, letterbox bars, the line set as a subtitle just above the lower bar."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"], 0.5) if photo else Image.new("RGB", (w, h), pal["dark"])
    toned = ImageOps.colorize(ImageOps.grayscale(base), black="#0B1418", mid="#5E6B66", white="#F4DDBD")
    img = vignette(Image.blend(grade(base, 0.84, 1.1, 0.8), toned, 0.42), 0.55)
    bar = round(h * 0.11)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, bar), fill="#050505")
    d.rectangle((0, h - bar, w, h), fill="#050505")
    st, lines = fit(tokens(c["text"]), lambda s: Style(o["face"] or "sans", s, "#FFFFFF", leading=1.3),
                    w * 0.84, h * 0.24, sizes(52 * u, 32 * u), 4)
    bh = block_h(st, len(lines))
    top = h - bar - 64 * u - bh if o["position"] in ("auto", "bottom") else _place(o["position"], "center", h, bh)
    layer = Image.new("RGBA", (w, h))
    draw_lines(layer, st, lines, w / 2, top)
    lab = Style("label", 19 * u, "#FFFFFF", tracking=0.34, case="upper", alpha=150)
    if sub := sub_line(c):
        draw_lines(layer, lab, [tokens(sub.replace("— ", ""))], w / 2, (bar - lab.cap) / 2)
    return shadowed(grain(img, 0.11), layer, 0.9, 5 * u)


def polaroid(photo, c, pal, w, h, o):
    """An instant print taped to a sheet of paper, slightly crooked, the line written underneath in an italic serif."""
    u = w / 1080
    img = paper(w, h, mix("#DCD4C6", pal.get("light", "#E9E3D8"), 0.3))
    seed = _seed(c["text"])
    pw = round(w * 0.66)
    border = round(pw * 0.055)
    frame = Image.new("RGBA", (pw + 2 * border, pw + border + round(border * 3.6)), "#FBFAF6")
    if photo:
        pic = grade(cover(photo, pw, pw, o["subject"]), 1.02, 0.86, 0.8)
        pic = grain(Image.blend(pic, Image.new("RGB", pic.size, "#F2D7AE"), 0.14), 0.14)
    else:
        pic = Image.new("RGB", (pw, pw), pal["dark"])
    frame.paste(pic, (border, border))
    angle = -3.2 + (seed % 5 - 2) * 0.9
    tilted = frame.rotate(angle, resample=Image.BICUBIC, expand=True)
    x, y = (w - tilted.width) // 2, round(82 * u)
    shadow = Image.new("RGBA", (w, h))
    sh = Image.new("RGBA", tilted.size, (0, 0, 0, 0))
    sh.putalpha(tilted.getchannel("A").point(lambda v: round(v * 0.38)))
    shadow.paste(sh, (x + round(10 * u), y + round(16 * u)), sh)
    img = over(img, shadow.filter(ImageFilter.GaussianBlur(18 * u)))
    canvas = img.convert("RGBA")
    canvas.alpha_composite(tilted, (x, y))
    tape = Image.new("RGBA", (round(150 * u), round(46 * u)), (233, 223, 196, 170))
    for tx, ta in ((x + tilted.width * 0.12, 32), (x + tilted.width * 0.72, -28)):
        t = tape.rotate(ta + angle, resample=Image.BICUBIC, expand=True)
        canvas.alpha_composite(t, (round(tx), max(0, y - round(18 * u))))
    img = canvas.convert("RGB")
    area_top = y + tilted.height + 44 * u
    st, lines = fit(tokens(c["text"]), lambda s: Style(o["face"] or "serif-italic", s, "#262320", leading=1.16),
                    w * 0.78, h - area_top - 120 * u, sizes(70 * u, 34 * u), 5)
    lab = Style("label", 20 * u, "#4A453E", tracking=0.22, case="upper")
    gap = st.size * 0.55
    bh = block_h(st, len(lines)) + (gap + lab.cap if c["author"] else 0)
    top = area_top + max(0, (h - 110 * u - area_top - bh) / 2)
    layer = Image.new("RGBA", (w, h))
    yy = draw_lines(layer, st, lines, w / 2, top)
    if c["author"]:
        draw_lines(layer, lab, [tokens(c["author"])], w / 2, yy + gap)
    return over(img, layer)


def swiss(photo, c, pal, w, h, o):
    """A Swiss poster on one strong colour: huge flush-left capitals sitting on the lower rule, thin rules and two
    small labels framing them. No photograph: the type is the image."""
    u = w / 1080
    ground = tone(pal.get("primary", "#C8452B"), 0.5, 0.78)
    ink = INK if _light(ground) > 0.56 else "#F6F3EE"
    img = grain(Image.new("RGB", (w, h), ground), 0.05)
    m = 76 * u
    head, lines = fit(tokens(c["text"]),
                      lambda s: Style(o["face"] or "grotesk", s, ink, leading=1.04, tracking=-0.01, case="upper"),
                      w - 2 * m, h * 0.6, sizes(118 * u, 40 * u), 8)
    lab = Style("label", 20 * u, ink, tracking=0.3, case="upper", alpha=220)
    layer = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(layer)
    rule_t, rule_b = m + 44 * u, h - m - 44 * u
    for yy in (rule_t, rule_b):
        d.rectangle((m, yy, w - m, yy + max(2, round(2.5 * u))), fill=rgba(ink, 230))
    if sub := sub_line(c):
        draw_lines(layer, lab, [tokens(sub.replace("— ", ""))], m, m, "left")
    d.rectangle((w - m - 26 * u, m, w - m, m + 26 * u), fill=rgba(ink, 230))
    bh = block_h(head, len(lines))
    top = rule_b - 40 * u - bh if o["position"] in ("auto", "bottom") else _place(o["position"], "center", h, bh)
    draw_lines(layer, head, lines, m, max(top, rule_t + 40 * u), "left")
    return over(img, layer)

RENDER = {"noir": noir, "paper": paper_note, "whisper": whisper, "statement": statement, "classic": classic,
          "split": split, "stack": stack, "notes": notes, "highlight": highlight, "riso": riso, "subtitle": subtitle,
          "polaroid": polaroid, "swiss": swiss}


def compose(design: str, photo: Image.Image | None, quote: dict, palette: dict, w: int, h: int, *,
            subject: str = "center", face: str = "auto", position: str = "auto") -> Image.Image:
    opts = {"face": face if face in FACES and face != "auto" else None, "position": position, "subject": subject}
    return RENDER[design](photo, copy_for(quote), palette, w, h, opts)
