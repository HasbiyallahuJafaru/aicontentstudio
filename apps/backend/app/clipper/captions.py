"""Karaoke captions as ASS subtitles: short word groups, the spoken word highlighted, burned by ffmpeg."""
from pathlib import Path

from app.clipper.tighten import bare

FONTS = Path(__file__).parent / "assets" / "fonts"  # Montserrat ExtraBold, SIL OFL (assets/fonts/OFL.txt)

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Montserrat,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,7,3,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
HIGHLIGHT = "&H0000E6FF&"  # ASS colours are BGR: warm yellow, the word being spoken
EMPHASIS = "&H003D7AFF&"  # orange (#FF7A3D): the clip's key words, clearly apart from the spoken-word yellow
BASE = "&H00FFFFFF&"
POP = "{\\fscx82\\fscy82\\t(0,120,\\fscx100\\fscy100)}"  # a new word group scales in over 120 ms


def ass_escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def captions(words: list[dict], start: float, end: float, width: int = 1080, height: int = 1920,
             emphasis=()) -> str:
    """ASS subtitles from the real transcript words: short groups that pop in, the spoken word highlighted, the
    clip's `emphasis` words coloured. The header's play resolution follows the clip's orientation, and the bottom
    margin stays the same share of the height."""
    header = ASS_HEADER.format(width=width, height=height, margin_v=round(560 * height / 1920))
    keys = {bare(e) for e in emphasis} - {""}

    def ts(t):
        cs = max(0, round((t - start) * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"

    groups = []
    for w in (w | {"word": ass_escape(w["word"])} for w in words if start <= w["start"] < end and w["word"]):
        g = groups[-1] if groups else []
        if (g and len(g) < 3 and len(" ".join(x["word"] for x in g)) + len(w["word"]) < 18
                and w["start"] - g[-1]["end"] < 0.5 and g[-1]["word"][-1] not in ".?!,"):
            g.append(w)
        else:
            groups.append([w])

    lines = [header]
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else end
        for i, w in enumerate(g):
            until = g[i + 1]["start"] if i + 1 < len(g) else min(next_start, w["end"] + 0.5)
            # colours reset with \c, not \r: \r would also reset the pop's scale mid-line
            text = " ".join(f"{{\\c{HIGHLIGHT}}}{x['word']}{{\\c{BASE}}}" if x is w else
                            f"{{\\c{EMPHASIS}}}{x['word']}{{\\c{BASE}}}" if bare(x["word"]) in keys else x["word"]
                            for x in g)
            lines.append(f"Dialogue: 0,{ts(w['start'])},{ts(until)},Caption,,0,0,0,,{POP if i == 0 else ''}{text}")
    return "\n".join(lines) + "\n"
