"""The voiced quote video's words (owner 2026-11-12, after @soulxsigh and the reference posts the owner shared):
the narrator opens with "Seneca once wrote:", reads the quote, names the book, then gives the lesson. The words
appear one at a time as they are spoken, in place, the way text typed into TikTok or Instagram looks: small, regular,
sentence case, white with a soft shadow, in the upper third over the photo ("In Quran, Allah says:" then the line).
The opening sits on its own line, the quote builds under it, and the book lands as a small "[Meditations]" citation.
The finished quote then stays on screen through the lesson: no cut to the designed post.

`script` writes what the voice reads and remembers which words are which; `timeline` lines those words up with the
narration's real word timings; `ass` turns that into the subtitle file render_video burns."""
import difflib
import re
import wave

SECTION_MAX = 14  # words: a longer sentence is split at its commas so the reveal never holds a paragraph
HOLD = 0.7  # seconds of breath between the quote's sentences; inserted only where the voice ran straight on
FONT = "Instrument Sans"  # bundled OFL Regular: the plain sans of text typed in-app, never bold or capitals
SIZE = 0.027  # of the frame height (~52 px at 1920): small, like the reference posts
TOP = 0.16    # the block starts this far down: the upper third, clear of the platform's top bar
SIDE = 0.10   # side margins


def sections(text: str) -> list[str]:
    """The quote's beats: sentences, then clauses for long ones; a 1-2 word scrap joins its neighbour."""
    out = []
    for sentence in re.split(r"(?<=[.!?;:])\s+", " ".join(text.split())):
        words = sentence.split()
        if len(words) <= SECTION_MAX:
            out.append(sentence)
            continue
        cur = []
        for w in words:
            cur.append(w)
            if w.endswith(",") and len(cur) >= 4:
                out.append(" ".join(cur))
                cur = []
        if cur:
            out.append(" ".join(cur))
    merged = []
    for s in out:
        if merged and (len(s.split()) < 3 or len(merged[-1].split()) < 3):
            merged[-1] += " " + s
        else:
            merged.append(s)
    return [s for s in merged if s]


def script(quote: dict, lesson: str = "") -> tuple[str, list[dict]]:
    """(text for the voice, parts). Parts are {kind: intro|quote|source|lesson, text, words: [start, end)} over
    the text's whitespace tokens, in reading order."""
    author, source = (quote.get("author") or "").strip(), (quote.get("source") or "").strip()
    parts = []
    if author:
        # a colon, not "...": the ellipsis read as a long stiff pause (owner 2026-11-12: "slow and robotic")
        parts.append({"kind": "intro", "text": f"{author} once {'wrote' if source else 'said'}:"})
    parts += [{"kind": "quote", "text": s} for s in sections(quote["text"])]
    if source:
        parts.append({"kind": "source", "text": source.rstrip(".") + "."})
    if lesson.strip():
        parts.append({"kind": "lesson", "text": lesson.strip()})
    n = 0
    for p in parts:
        k = len(p["text"].split())
        p["words"] = [n, n + k]
        n += k
    # a blank line between beats: spoken() turns each line into a breath, so the sections get their own pause
    lines, prev = [], None
    for p in parts:
        if p["kind"] == "quote" and prev == "quote":
            lines[-1] += " " + p["text"]
        else:
            lines.append(p["text"])
        prev = p["kind"]
    return "\n\n".join(lines), parts


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def timeline(text: str, heard: list[dict], duration: float) -> list[tuple[float, float]]:
    """(start, end) for every whitespace token of `text`, taken from the transcribed words where they match and
    interpolated between matches where the transcript heard something else (a name, a number)."""
    tokens = text.split()
    times: list[tuple[float, float] | None] = [None] * len(tokens)
    a, b = [_norm(t) for t in tokens], [_norm(h["word"]) for h in heard]
    for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(m.size):
            h = heard[m.b + k]
            times[m.a + k] = (float(h["start"]), float(h["end"]))
    # fill the gaps: spread each run of unmatched tokens evenly between the matched words around it
    i = 0
    while i < len(tokens):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(tokens) and times[j] is None:
            j += 1
        lo = times[i - 1][1] if i else 0.0
        hi = times[j][0] if j < len(tokens) else duration
        step = max(hi - lo, 0.0) / (j - i)
        for k in range(i, j):
            times[k] = (lo + step * (k - i), lo + step * (k - i + 1))
        i = j
    return times  # type: ignore[return-value]


def stretch(wav_path, parts: list[dict], times: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Give every finished quote section its moment: where the narrator moved on sooner than HOLD seconds, insert
    silence into the narration WAV (in place) between the section's last word and the next word, and return the
    word times shifted to match. The pause is the point: the reveal reads at the pace of the spoken-word pages.

    A transcript often stretches a word's end across the pause after it, so the section's real end is found in the
    audio itself: the last stretch of voice before the next word."""
    with wave.open(str(wav_path), "rb") as w:
        params, rate = w.getparams(), w.getframerate()
        frame = w.getsampwidth() * w.getnchannels()
        audio = w.readframes(w.getnframes())
    times = list(times)
    cuts = []  # (at seconds, silence to add)
    for p in parts:
        if p["kind"] != "quote" or p["words"][1] >= len(times):
            continue
        last_word = p["words"][1] - 1
        start, nxt = times[last_word][0], times[p["words"][1]][0]
        end = min(_voice_end(audio, rate, frame, params.sampwidth, start, nxt), times[last_word][1])
        times[last_word] = (start, end)
        if nxt - end < HOLD:
            cuts.append(((end + nxt) / 2, HOLD - (nxt - end)))
    if not cuts:
        return times
    out, last = bytearray(), 0
    for at, add in cuts:
        k = int(at * rate) * frame
        out += audio[last:k] + bytes(int(add * rate) * frame)
        last = k
    out += audio[last:]
    with wave.open(str(wav_path), "wb") as w:
        w.setparams(params)
        w.writeframes(bytes(out))

    def shift(t: float, starts: bool) -> float:  # a word starting on a cut moves with it, one ending there stays
        return t + sum(add for at, add in cuts if (at <= t if starts else at < t))
    return [(shift(a, True), shift(b, False)) for a, b in times]


def _voice_end(audio: bytes, rate: int, frame: int, width: int, start: float, stop: float) -> float:
    """When the voice in [start, stop] goes quiet for good: the end of the last 20 ms window with speech in it."""
    if width != 2 or stop <= start:  # TTS PCM is 16-bit; anything else keeps the transcript's time
        return stop
    from array import array
    win = max(int(rate * 0.02), 1)
    lo, hi = int(start * rate), int(stop * rate)
    pcm = array("h", audio[lo * frame:hi * frame])
    step = frame // 2  # samples per frame (channels)
    end = start
    for k in range(0, hi - lo, win):
        chunk = pcm[k * step:(k + win) * step:step]
        if chunk and sum(abs(x) for x in chunk) / len(chunk) > 400:  # ~-38 dBFS mean: speech, not room tone
            end = start + (k + win) / rate
    return min(end + 0.08, stop)


QUOTES = "\"\u201c\u201d"  # quote marks never shown on screen


def _t(s: float) -> str:
    s = max(s, 0.0)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "⧵").replace("{", "(").replace("}", ")")


def finished(parts: list[dict], times: list[tuple[float, float]]) -> float:
    """When the whole quote (and its "[book]" citation) is on screen: the start of the last word that appears."""
    last = max(p["words"][1] - 1 for p in parts if p["kind"] in ("intro", "quote", "source"))
    return times[last][0]


def ass(parts: list[dict], times: list[tuple[float, float]], w: int, h: int, until: float,
        bright: bool = False) -> str:
    """The subtitle file: the opening line, then the quote, then the "[book]" citation, every word appearing (a 180
    ms fade) as it is spoken and staying; the finished block holds until `until`. Each event carries the whole block
    with the words not yet spoken fully transparent, so the layout never moves while it fills in. On a `bright`
    picture the words carry a soft dark halo (a blurred outline) so white text reads on a pale sky."""
    shown = [p for p in parts if p["kind"] in ("intro", "quote", "source")]
    lines: list[list[int]] = []  # each line: indexes into `flat`
    flat: list[tuple[str, int]] = []  # (word as shown, index into times)
    prev = None
    for p in shown:
        toks = p["text"].split()
        idx = list(range(p["words"][0], p["words"][1]))
        if p["kind"] == "source":  # the book lands as one small citation, as the narrator names it
            toks, idx = [f"[{p['text'].rstrip('.')}]"], idx[:1]
        start = len(flat)
        flat += [(_esc(t).strip(QUOTES), i) for t, i in zip(toks, idx)]
        if p["kind"] == "quote" and prev == "quote":
            lines[-1] += range(start, len(flat))  # the quote's sections read as one paragraph
        else:
            lines.append(list(range(start, len(flat))))
        prev = p["kind"]
    chars = sum(len(word) + 1 for word, _ in flat)
    size = round(h * SIZE * min(1.0, (240 / max(chars, 1)) ** 0.5))  # a long quote steps down rather than overflow
    cite = round(size * 0.8)
    # a bright picture: a wide, faint, well-blurred glow (a hard dark outline read as outlined text, not a shadow)
    edge, outline = ("&H98000000", max(3, h // 400)) if bright else ("&HA0000000", max(1, h // 1100))
    halo = f"\\blur{max(4, h // 240)}" if bright else ""
    source_line = len(lines) - 1 if shown and shown[-1]["kind"] == "source" else -1
    events = []
    for k, (_, ti) in enumerate(flat):
        start = times[ti][0]
        end = times[flat[k + 1][1]][0] if k + 1 < len(flat) else until
        if end <= start:
            continue
        out = []
        for li, line in enumerate(lines):
            words = []
            for j in line:
                tag = ("{\\alpha&H00&}" if j < k else "{\\alpha&HFF&\\t(0,180,\\alpha&H00&)}" if j == k
                       else "{\\alpha&HFF&}")
                words.append(tag + flat[j][0])
            text = " ".join(words)
            out.append(f"{{\\fs{cite}}}" + text if li == source_line else text)
        events.append(f"Dialogue: 0,{_t(start)},{_t(end)},Words,,0,0,0,,{{\\fs{size}{halo}}}" + "\\N".join(out))
    side, top = round(w * SIDE), round(h * TOP)
    # on a dark picture: a thin outline and a small shadow. On a bright one: a wider, softer, darker halo
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Words,{FONT},{size},&H00FFFFFF,&H00FFFFFF,{edge},&H80000000,0,0,0,0,100,100,0,0,1,{outline},{max(1, h // 900)},7,{side},{side},{top},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(events) + "\n"
