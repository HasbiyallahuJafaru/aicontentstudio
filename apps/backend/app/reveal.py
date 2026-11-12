"""The voiced quote video's words (owner 2026-11-12, after @soulxsigh): the narrator opens with "Seneca once wrote",
reads the quote, names the book, then gives the lesson. While he reads the quote, two or three words at a time sit
in the centre of the frame, in step with his voice; when he finishes a section (a sentence or clause), the whole
section shows; when the quote is done, the designed post itself takes the screen for the book and the lesson.

`script` writes what the voice reads and remembers which words are which; `timeline` lines those words up with the
narration's real word timings; `ass` turns that into the subtitle file render_video burns."""
import difflib
import re
import wave

SECTION_MAX = 14  # words: a longer sentence is split at its commas so the reveal never holds a paragraph
HOLD = 1.6  # seconds a finished section shows whole; the voice waits for it (stretch)
FONT = "Instrument Serif"  # bundled OFL (assets/fonts): a quiet book serif, the look of the spoken-word pages


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


def chunks(words: list[str]) -> list[list[int]]:
    """Indexes of 2-3 word groups: a group closes at three words or at punctuation, a lone last word joins the
    group before it."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if len(cur) == 3 or (len(cur) >= 2 and w[-1] in ",.;:!?—-…"):
            groups.append(cur)
            cur = []
    if cur:
        if groups and len(cur) == 1:
            groups[-1] += cur
        else:
            groups.append(cur)
    return groups


def script(quote: dict, lesson: str = "") -> tuple[str, list[dict]]:
    """(text for the voice, parts). Parts are {kind: intro|quote|source|lesson, text, words: [start, end)} over
    the text's whitespace tokens, in reading order."""
    author, source = (quote.get("author") or "").strip(), (quote.get("source") or "").strip()
    parts = []
    if author:
        parts.append({"kind": "intro", "text": f"{author} once {'wrote' if source else 'said'}..."})
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


def _t(s: float) -> str:
    s = max(s, 0.0)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "⧵").replace("{", "(").replace("}", ")")


def ass(parts: list[dict], times: list[tuple[float, float]], w: int, h: int) -> tuple[str, float]:
    """(subtitle file, when the post should take over). The intro and every quote section reveal 2-3 words at a
    time; a finished quote section then shows whole until the next one starts; the last one holds until the post."""
    words_of = [p["text"].split() for p in parts]
    reveal = [i for i, p in enumerate(parts) if p["kind"] in ("intro", "quote")]
    quotes = [i for i, p in enumerate(parts) if p["kind"] == "quote"]
    end_all = times[-1][1] if times else 0.0
    last_q = parts[quotes[-1]]["words"][1] - 1
    nxt = next((p["words"][0] for p in parts if p["kind"] in ("source", "lesson")), None)
    # the last section shows whole for HOLD seconds, then the post arrives as the book is named
    post_at = max(times[last_q][1] + HOLD, times[nxt][0] if nxt is not None else 0.0)
    post_at = min(post_at, max(end_all, times[last_q][1] + HOLD))
    big, small = round(h * 0.05), round(h * 0.037)
    events = []
    for n, i in enumerate(reveal):
        p, toks = parts[i], words_of[i]
        base = p["words"][0]
        groups = chunks(toks)
        if p["kind"] == "intro" and len(toks) > 2:  # the name on its own, then "once wrote"
            groups = [list(range(len(toks) - 2)), [len(toks) - 2, len(toks) - 1]]
        sec_end = times[base + len(toks) - 1][1]
        later = reveal[n + 1] if n + 1 < len(reveal) else None
        sec_next = times[parts[later]["words"][0]][0] if later is not None else post_at
        for g_i, g in enumerate(groups):
            start = times[base + g[0]][0]
            if g_i + 1 < len(groups):
                end = times[base + groups[g_i + 1][0]][0]
            else:  # the last group stays until the section shows whole (or the next part begins, for the intro)
                end = sec_end + 0.12 if p["kind"] == "quote" else sec_next
            text = _esc(" ".join(toks[k] for k in g)).strip("\"“”")
            if p["kind"] == "intro":  # "once wrote..." reads aloud as a pause; on screen it is just "once wrote"
                text = text.rstrip(".")
            events.append(f"Dialogue: 0,{_t(start)},{_t(max(end, start + 0.2))},Chunk,,0,0,0,,"
                          r"{\fad(140,0)\t(0,260,\fscx100\fscy100)\fscx94\fscy94}" + text)
        if p["kind"] == "quote":
            hold_end = max(sec_next, sec_end + 0.4)
            text = _esc(p["text"]).strip("\"“”")
            events.append(f"Dialogue: 0,{_t(sec_end + 0.12)},{_t(hold_end)},Section,,0,0,0,,"
                          r"{\fad(220,160)}" + text)
    margin = round(w * 0.12)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Chunk,{FONT},{big},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,0,{max(2, h // 640)},5,{margin},{margin},0,1
Style: Section,{FONT},{small},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,{max(2, h // 640)},5,{margin},{margin},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(events) + "\n", post_at
