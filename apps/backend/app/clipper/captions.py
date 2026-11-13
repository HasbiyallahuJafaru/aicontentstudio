"""Burned captions as ASS subtitles, from the real word timings, in a chosen style (owner brief 2026-11-07: the
subtitles get the same design care as the stills, with choices for style, font, position, size and colour).

Styles, each a known high-performing short-form look:
- karaoke: 2-3 word groups that pop in, the spoken word lit (the clipper's original look, the default);
- pop: one word at a time in big condensed capitals, bouncing in, key words in the highlight colour;
- clean: calm sentence-case phrases with a soft shadow, fading in (documentary / cinematic);
- boxed: phrases on a solid plate, the spoken word lit (TikTok native);
- minimal: small lowercase phrases, light weight, soft shadow (hopecore / spoken word);
- serif: italic serif phrases with key words in the highlight (editorial, stoic, book quotes);
- marker: white phrases, a solid block of the highlight colour sliding under the spoken word (2026's "highlight
  word" look, and the Marker word picture design in motion);
- duet: sentence-case sans, the key word turned to italic serif in the palette accent, each word blurring into
  focus in place as it is spoken (the editorial mixed type of the 2026 picture designs, in motion).
Placement follows the 2026 safe-zone research: lower captions sit in the Y 1200-1550 band of a 1920 frame, clear
of the bottom caption/username strip (320-450 px) and the right-hand button column (~160 px).
"""
import struct
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from app.clipper.tighten import FILLERS, bare
from app.design import FONTS_DIR, font, mix

FONTS = FONTS_DIR  # every bundled face (SIL OFL), handed to libass as fontsdir

CAPTION_FONTS = {"auto": "Matches the style", "montserrat": "Montserrat ExtraBold", "poster": "Big Shoulders",
                 "geometric": "Outfit Bold", "grotesk": "Bricolage Grotesque", "sans-bold": "Instrument Sans Bold",
                 "sans": "Instrument Sans", "serif-italic": "Instrument Serif Italic", "heavy": "Boldonse"}
HIGHLIGHTS = {"yellow": "#FFE600", "orange": "#FF7A3D", "green": "#8EE07A", "red": "#FF5A4E", "white": "#FFFFFF"}


class CaptionStyle(BaseModel):
    style: Literal["karaoke", "pop", "clean", "boxed", "minimal", "serif", "marker", "duet"] = "karaoke"
    font: Literal[tuple(CAPTION_FONTS)] = "auto"
    position: Literal["lower", "middle", "upper"] = "lower"
    size: Literal["small", "medium", "large"] = "medium"
    highlight: Literal["auto", "palette", "yellow", "orange", "green", "red", "white"] = "auto"
    case: Literal["auto", "upper", "lower", "as_spoken"] = "auto"


# per style: face, size at 1920 tall, case, grouping (words, chars), colouring mode, outline/shadow, plate, motion
PRESETS = {
    "karaoke": dict(font="montserrat", size=88, case=None, words=3, chars=18, mode="word", outline=7, shadow=3,
                    highlight="yellow", anim="pop"),
    "pop": dict(font="poster", size=138, case="upper", words=1, chars=14, mode="emphasis", outline=8, shadow=4,
                highlight="yellow", anim="bounce"),
    "clean": dict(font="sans-bold", size=66, case=None, words=7, chars=32, mode="none", outline=3, shadow=0,
                  soft=True, highlight="white", anim="fade"),
    "boxed": dict(font="geometric", size=72, case=None, words=4, chars=22, mode="word", outline=16, shadow=0,
                  box=True, highlight="yellow", anim="pop"),
    "minimal": dict(font="sans", size=58, case="lower", words=6, chars=30, mode="none", outline=3, shadow=0,
                    soft=True, highlight="white", anim="fade"),
    "serif": dict(font="serif-italic", size=84, case=None, words=5, chars=26, mode="emphasis", outline=3, shadow=0,
                  soft=True, highlight="palette", anim="fade"),
    "marker": dict(font="sans-bold", size=92, case=None, words=3, chars=20, mode="word", outline=3, shadow=0,
                   soft=True, highlight="palette", anim="rise", layout="marker"),
    "duet": dict(font="sans-bold", size=70, case=None, words=6, chars=30, mode="emphasis", outline=3, shadow=0,
                 soft=True, highlight="palette", anim="none", layout="duet"),
}
SIZES = {"small": 0.82, "medium": 1.0, "large": 1.2}

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},&H00FFFFFF,&H00FFFFFF,{outline_colour},&H99000000,{bold},{italic},0,0,100,100,0,0,{border},{outline},{shadow},{align},{margin_x},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
HIGHLIGHT = "&H0000E6FF&"  # ASS colours are BGR: warm yellow, the word being spoken
EMPHASIS = "&H003D7AFF&"  # orange (#FF7A3D): the clip's key words, clearly apart from the spoken-word yellow
BASE = "&H00FFFFFF&"
POP = "{\\fscx82\\fscy82\\t(0,120,\\fscx100\\fscy100)}"  # a new word group scales in over 120 ms
BOUNCE = "{\\fscx70\\fscy70\\t(0,90,\\fscx108\\fscy108)\\t(90,170,\\fscx100\\fscy100)}"
FADE = "{\\fad(140,100)\\blur6}"  # \blur softens the halo only: the fill stays sharp while there is an outline


def ass_colour(hex_rgb: str, alpha: int = 0) -> str:
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"&H{alpha:02X}{b}{g}{r}&".upper()


def ass_escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


NOT_REPEATS = {"that", "had", "is"}  # "I know that that is", "had had": real doubled words


def readable(words: list[dict]) -> list[dict]:
    """Captions are for reading, not a court transcript: fillers and cut-off words ("es-", "A--") go, and a word
    said twice in a row ("I I think") shows once, starting where the first one did."""
    out = []
    for w in words:
        b = bare(w["word"])
        if not b or b in FILLERS or w["word"].rstrip(".,?!").endswith("-"):
            continue
        if out and bare(out[-1]["word"]) == b and b not in NOT_REPEATS and w["start"] - out[-1]["end"] < 0.3:
            out[-1] = w | {"start": out[-1]["start"]}
            continue
        out.append(w)
    return out


def _face(key: str) -> tuple[str, int, int]:
    """ASS font name and bold/italic flags, read from the bundled file so libass matches exactly that file.
    A weight beyond Regular/Bold/Italic is part of the name libass knows (2026-11-12: "Montserrat" fell back to
    Arial Bold on every karaoke caption; "Montserrat ExtraBold" loads the bundled file, checked in libass's log)."""
    family, style = font(key, 40).getname()
    if style not in ("Regular", "Bold", "Italic", "Bold Italic"):
        family = f"{family} {style}"
    return family, -1 if "Bold" in style else 0, -1 if "Italic" in style else 0


def captions(words: list[dict], start: float, end: float, width: int = 1080, height: int = 1920,
             emphasis=(), style: CaptionStyle | dict | None = None, accent: str = "#E0B07A",
             plate: str = "#111111") -> str:
    """ASS subtitles from the real transcript words in `style` (default: the karaoke look). `emphasis` words get
    the highlight colour; `accent` is the project palette's accent (highlight "palette"); `plate` the boxed
    style's plate colour. The play resolution follows the clip's orientation and margins scale with height."""
    st = CaptionStyle.model_validate(style or {})
    p = PRESETS[st.style]
    face_key = p["font"] if st.font == "auto" else st.font
    family, bold, italic = _face(face_key)
    size = round(p["size"] * SIZES[st.size] * min(width, height) / 1080)  # same share of the short side
    case = p["case"] if st.case == "auto" else None if st.case == "as_spoken" else st.case
    hl_name = p["highlight"] if st.highlight == "auto" else st.highlight
    hl_hex = accent if hl_name == "palette" else HIGHLIGHTS[hl_name]
    hl = ass_colour(hl_hex)
    emph = EMPHASIS if hl != EMPHASIS else HIGHLIGHT  # key words stay apart from the spoken-word colour
    if p["mode"] == "emphasis":
        emph = hl
    align, margin_v = {"lower": (2, round(560 * height / 1920)), "middle": (5, 0),
                       "upper": (8, round(330 * height / 1920))}[st.position]
    box = p.get("box")
    outline_colour = ass_colour(plate, 0x30) if box else "&H70000000" if p.get("soft") else "&H00000000"
    header = ASS_HEADER.format(width=width, height=height, font=family, size=size, bold=bold, italic=italic,
                               outline_colour=outline_colour, border=3 if box else 1, outline=p["outline"],
                               shadow=p["shadow"], align=align, margin_v=margin_v,
                               margin_x=round(80 * min(width, height) / 1080),
                               margin_r=round((160 if height > width else 80) * min(width, height) / 1080))
    keys = ({bare(x) for e in emphasis for x in e.split()} - {""}) if p["mode"] != "none" else set()

    def ts(t):
        cs = max(0, round((t - start) * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"

    def cased(word):
        return word.upper() if case == "upper" else word.lower() if case == "lower" else word

    groups = []
    for w in (w | {"word": ass_escape(cased(w["word"]))}
              for w in readable([w for w in words if start <= w["start"] < end and w["word"]])):
        g = groups[-1] if groups else []
        if (g and len(g) < p["words"]
                and len(" ".join(x["word"] for x in g)) + len(w["word"]) < p["chars"]
                and w["start"] - g[-1]["end"] < 0.5 and g[-1]["word"][-1] not in ".?!,"):
            g.append(w)
        else:
            groups.append([w])
    if p["words"] == 1:  # a short word waits for the next instead of flashing alone
        merged = []
        for g in groups:
            if merged and len(merged[-1]) == 1 and len(merged[-1][0]["word"]) <= 3 \
                    and merged[-1][0]["word"][-1] not in ".?!," and g[0]["start"] - merged[-1][0]["end"] < 0.5:
                merged[-1] = merged[-1] + g
            else:
                merged.append(g)
        groups = merged

    def coloured(x, lit=False):
        if lit:
            return f"{{\\c{hl}}}{x['word']}{{\\c{BASE}}}"
        if bare(x["word"]) in keys:
            return f"{{\\c{emph}}}{x['word']}{{\\c{BASE}}}"
        return x["word"]

    lines = [header]
    if p.get("layout") == "marker":
        box = (round(80 * min(width, height) / 1080),
               width - round((160 if height > width else 80) * min(width, height) / 1080))
        return "\n".join(lines + _marker(groups, end, face_key, size, hl_hex, box, height, margin_v, st.position,
                                         ts)) + "\n"
    if p.get("layout") == "duet":  # the thin italic needs a lighter tint than a bold word to hold its contrast
        return "\n".join(lines + _duet(groups, end, keys, family, ass_colour(mix(hl_hex, "#FFFFFF", 0.4)), ts)) + "\n"
    anim = {"pop": POP, "bounce": BOUNCE, "fade": FADE}[p["anim"]]
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else end
        if p["mode"] == "word":
            for i, w in enumerate(g):
                until = g[i + 1]["start"] if i + 1 < len(g) else min(next_start, w["end"] + 0.5)
                # colours reset with \c, not \r: \r would also reset the pop's scale mid-line
                text = " ".join(coloured(x, x is w) for x in g)
                lines.append(f"Dialogue: 0,{ts(w['start'])},{ts(until)},Caption,,0,0,0,,"
                             f"{anim if i == 0 else ''}{text}")
        else:
            until = min(next_start, g[-1]["end"] + 0.5)
            text = " ".join(coloured(x) for x in g)
            lines.append(f"Dialogue: 0,{ts(g[0]['start'])},{ts(until)},Caption,,0,0,0,,{anim}{text}")
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=32)
def _win_metrics(face_key: str) -> tuple[float, float]:
    """(usWinAscent, usWinDescent) in em, read from the font's OS/2 table: libass sizes a font so that their sum is
    the ASS font size (measured 2026-11-13: PIL's own metrics put the block ~10% off the word)."""
    from app.design import FACES
    data = (FONTS / FACES[face_key]).read_bytes()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        tables[tag] = off
    upem = struct.unpack(">H", data[tables[b"head"] + 18:tables[b"head"] + 20])[0]
    asc, desc = struct.unpack(">HH", data[tables[b"OS/2"] + 74:tables[b"OS/2"] + 78])
    return asc / upem, desc / upem


def _ass_font(face_key: str, ass_size: int):
    """The PIL font that measures exactly what libass draws at `ass_size`, and its baseline below the line top."""
    asc, desc = _win_metrics(face_key)
    em = ass_size / (asc + desc)
    return font(face_key, max(6, round(em))), asc * em


def _marker(groups, end, face_key, size, block_hex, box, height, margin_v, position, ts) -> list[str]:
    """Each phrase laid out by hand (\\pos) so a solid block can sit exactly under the spoken word and glide to the
    next one: the block moves and resizes over 110 ms, the phrase rises into place over 160 ms."""
    from app.design import _light
    left, right = box
    ink = ass_colour("#141414" if _light(block_hex) > 0.5 else "#FFFFFF")
    out = []
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else end
        s = size
        f, base = _ass_font(face_key, s)
        widths = [f.getlength(x["word"]) for x in g]
        total = sum(widths) + f.getlength(" ") * (len(g) - 1)
        if total > right - left:  # a long phrase steps down in size instead of wrapping
            s = int(s * (right - left) / total)
            f, base = _ass_font(face_key, s)
            widths = [f.getlength(x["word"]) for x in g]
            total = sum(widths) + f.getlength(" ") * (len(g) - 1)
        cap = -f.getbbox("H", anchor="ls")[1]
        x0 = round((left + right) / 2 - total / 2)
        top = {"lower": height - margin_v - s, "upper": margin_v}.get(position, round((height - s) / 2))
        starts, cx = [], x0
        for wd in widths:
            starts.append(cx)
            cx += wd + f.getlength(" ")
        padx = f.size * 0.2
        bh = cap + f.size * 0.42  # cap height plus room for descenders
        rad = bh * 0.16
        by = top + base - cap / 2 + f.size * 0.07  # centred on the capitals, nudged down for descenders
        for i, w in enumerate(g):
            until = g[i + 1]["start"] if i + 1 < len(g) else min(next_start, w["end"] + 0.5)
            bw = widths[i] + 2 * padx
            bx = starts[i] + widths[i] / 2
            path = (f"m {rad:.0f} 0 l {bw - rad:.0f} 0 b {bw:.0f} 0 {bw:.0f} 0 {bw:.0f} {rad:.0f} "
                    f"l {bw:.0f} {bh - rad:.0f} b {bw:.0f} {bh:.0f} {bw:.0f} {bh:.0f} {bw - rad:.0f} {bh:.0f} "
                    f"l {rad:.0f} {bh:.0f} b 0 {bh:.0f} 0 {bh:.0f} 0 {bh - rad:.0f} l 0 {rad:.0f} b 0 0 0 0 {rad:.0f} 0")
            if i == 0:
                motion = f"\\pos({bx:.0f},{by:.0f})\\fscx70\\fscy70\\t(0,130,\\fscx100\\fscy100)"
            else:
                pbx, pbw = starts[i - 1] + widths[i - 1] / 2, widths[i - 1] + 2 * padx
                motion = (f"\\move({pbx:.0f},{by:.0f},{bx:.0f},{by:.0f},0,110)\\fscx{100 * pbw / bw:.0f}"
                          f"\\t(0,110,\\fscx100)")
            out.append(f"Dialogue: 0,{ts(w['start'])},{ts(until)},Caption,,0,0,0,,"
                       f"{{\\an5{motion}\\p1\\bord0\\shad0\\blur0.6\\1c{ass_colour(block_hex)}}}{path}")
            words = " ".join(f"{{\\1c{ink}\\3a&HFF&}}{x['word']}{{\\1c{BASE}\\3a&H70&}}" if x is w else x["word"]
                             for x in g)
            rise = (f"\\move({x0},{top + round(s * 0.18)},{x0},{top},0,160)\\fad(110,0)" if i == 0
                    else f"\\pos({x0},{top})")
            out.append(f"Dialogue: 1,{ts(w['start'])},{ts(until)},Caption,,0,0,0,,{{\\an7{rise}\\fs{s}\\blur3}}{words}")
    return out


def _duet(groups, end, keys, base_family, accent_ass, ts) -> list[str]:
    """Mixed type: the key word (or, failing one, the phrase's last content word when it ends a sentence) set in
    the italic serif in the accent; words appear in place as spoken, each one blurring into focus, so the layout
    never moves."""
    from app.design import beat, tokens
    serif, _, _ = _face("serif-italic")
    out = []
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else end
        stressed = [bare(x["word"]) in keys for x in g]
        if not any(stressed) and g[-1]["word"][-1] in ".!?":
            stressed = [e for _, e in beat(tokens(" ".join(x["word"] for x in g)))]

        def styled(x, e):
            if e:
                # a serif's hairlines drown in the soft outline: a thinner, fainter one keeps the italic legible
                return (f"{{\\fn{serif}\\i1\\b0\\1c{accent_ass}\\fscx134\\fscy134\\bord2\\3a&H50&}}{x['word']}"
                        f"{{\\fn{base_family}\\i0\\b1\\1c{BASE}\\fscx100\\fscy100\\bord3\\3a&H70&}}")
            return x["word"]

        for k, w in enumerate(g):
            until = g[k + 1]["start"] if k + 1 < len(g) else min(next_start, w["end"] + 0.6)
            parts = []
            for j, (x, e) in enumerate(zip(g, stressed)):
                tag = ("{\\alpha&H00&\\blur3}" if j < k else "{\\alpha&HFF&\\blur9\\t(0,190,\\alpha&H00&\\blur3)}"
                       if j == k else "{\\alpha&HFF&}")
                parts.append(tag + styled(x, e))
            out.append(f"Dialogue: 0,{ts(w['start'])},{ts(until)},Caption,,0,0,0,,{' '.join(parts)}")
    return out
