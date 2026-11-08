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
           "classic": "Classic serif", "split": "Editorial split", "stack": "Fitted stack"}
GENRE_DESIGNS = {"hope": ["whisper", "paper", "classic"], "speech": ["noir", "stack", "paper"],
                 "stoic": ["classic", "statement", "noir"], "history": ["classic", "split", "noir"],
                 "books": ["classic", "paper", "split"], "cinema": ["whisper", "noir", "split"]}
COMPOSITION = {"minimal": "whisper", "bold": "stack", "editorial": "split", "centered": "classic"}
SHORT_ONLY = {"statement": 12, "stack": 14, "whisper": 20}  # words: past this the design stops reading well
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


def copy_for(quote: dict) -> dict:
    """The quote split into the parts a designer works with. `emphasis` and `kicker` come from the writer when it
    gave them; otherwise a short final sentence ("Live it.") is the emphasis."""
    text = " ".join(quote["text"].split())
    emphasis = " ".join((quote.get("emphasis") or "").split())
    if not emphasis:
        parts = re.split(r"(?<=[.!?])\s+", text)
        if len(parts) >= 2 and len(parts[-1].split()) <= 4:
            emphasis = parts[-1]
    if emphasis and _norm(emphasis) not in _norm(text):
        emphasis = ""
    return {"text": text, "author": (quote.get("author") or "").strip(),
            "kicker": " ".join((quote.get("kicker") or "").split()), "emphasis": emphasis}


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


def tokens(text: str, emphasis: str = "") -> list[tuple[str, bool]]:
    words = text.split()
    flags = [False] * len(words)
    if emphasis:
        ew = [_norm(w) for w in emphasis.split()]
        for i in range(len(words) - len(ew) + 1):
            if [_norm(w) for w in words[i:i + len(ew)]] == ew:
                flags[i:i + len(ew)] = [True] * len(ew)
                break
    return list(zip(words, flags))


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
    return c["kicker"] or (f"— {c['author']}" if c["author"] else "")


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
    st, lines = fit(tokens(c["text"], c["emphasis"]),
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

    toks = tokens(c["text"], c["emphasis"])
    if not any(e for _, e in toks):  # no emphasis given: the longest word carries the poster
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
    """Magazine page: the photograph above, a solid panel in the palette's dark below, a tracked kicker in the
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
    dark scene, the emphasis lines in the accent."""
    u = w / 1080
    base = cover(photo, w, h, o["subject"]) if photo else Image.new("RGB", (w, h), pal["dark"])
    img = vignette(grade(base, 0.40, 1.12, 0.6), 0.7)
    face, acc, m = o["face"] or "poster", accent(pal), 84 * u
    measure, gap = w - 2 * m, 16 * u
    toks = tokens(c["text"], c["emphasis"])

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
    top = _place(o["position"], "center", h, height, 0.14, 0.88)
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
    return shadowed(grain(img, 0.08), layer, 0.45, 20 * u)


RENDER = {"noir": noir, "paper": paper_note, "whisper": whisper, "statement": statement, "classic": classic,
          "split": split, "stack": stack}


def compose(design: str, photo: Image.Image | None, quote: dict, palette: dict, w: int, h: int, *,
            subject: str = "center", face: str = "auto", position: str = "auto") -> Image.Image:
    opts = {"face": face if face in FACES and face != "auto" else None, "position": position, "subject": subject}
    return RENDER[design](photo, copy_for(quote), palette, w, h, opts)
