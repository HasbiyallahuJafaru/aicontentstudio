"""Bulk quotes from a spreadsheet export: CSV, TSV or semicolon files, with a quote column and an optional author
column, or quotes alone. Returns editable "quote — author" lines for the Create page's quote box, plus every row
it skipped and why, so nothing disappears silently."""
import base64
import csv
import io
import re

from app.errors import UserError

MAX_QUOTES = 100
MAX_LEN = 180  # a quote must fit the still designs (schemas.Quote caps text at 180)
MAX_BYTES = 2_000_000
QUOTE_HEADS = {"quote", "quotes", "text", "line", "lines", "content", "caption", "saying"}
AUTHOR_HEADS = {"author", "authors", "by", "source", "attribution", "name", "who", "speaker"}
WRAPPERS = "\"'“”‘’«»„ \t"


def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")  # Excel's "CSV" on Windows


def _clean_quote(s: str) -> str:
    return " ".join(s.split()).strip(WRAPPERS).strip()


def _clean_author(s: str) -> str:
    return " ".join(s.split()).lstrip("—–-~ ").strip(WRAPPERS).strip()


def _looks_like_name(s: str) -> bool:
    """A second column is an author only when it reads like one: short, and not a sentence."""
    s = _clean_author(s)
    return 0 < len(s) <= 60 and len(s.split()) <= 6 and not s.endswith((".", "!", "?"))


def from_csv(data_b64: str = "", text: str = "") -> dict:
    raw = base64.b64decode(data_b64) if data_b64 else text.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise UserError("That file is too big for a quote list.", f"{len(raw)} bytes; the limit is {MAX_BYTES}.")
    body = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(body[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [(n, [c.strip() for c in r]) for n, r in enumerate(csv.reader(io.StringIO(body), dialect), 1)]
    rows = [(n, r) for n, r in rows if any(r)]
    if not rows:
        raise UserError("That file has no quotes in it.", "Every row was empty.")

    heads = [c.lower().strip(WRAPPERS) for c in rows[0][1]]
    qi = next((i for i, h in enumerate(heads) if h in QUOTE_HEADS), None)
    ai = next((i for i, h in enumerate(heads) if h in AUTHOR_HEADS), None)
    header = qi is not None or ai is not None
    if header:
        rows = rows[1:]
        qi = qi if qi is not None else (1 if ai == 0 else 0)
        whole_line = False
    else:
        # no header: two columns are quote + author only if the second column reads like names; otherwise each
        # row is one quote that happened to contain the delimiter ("Life has no script, live it.")
        second = [r[1] for _, r in rows if len(r) > 1 and r[1]]
        qi, ai = 0, 1
        whole_line = not second or sum(map(_looks_like_name, second)) < 0.6 * len(second) or \
            any(len([c for c in r if c]) > 2 for _, r in rows)
    delim = getattr(dialect, "delimiter", ",")

    quotes, skipped, seen, authors = [], [], {}, 0
    for n, r in rows:
        if whole_line:
            q, a = _clean_quote(f"{delim} ".join(c for c in r if c)), ""
        else:
            q = _clean_quote(r[qi]) if qi < len(r) else ""
            a = _clean_author(r[ai]) if ai is not None and ai < len(r) else ""
        if not q:
            skipped.append({"row": n, "reason": "no quote in this row"})
            continue
        if len(q) < 3:
            skipped.append({"row": n, "reason": "too short"})
            continue
        if len(q) > MAX_LEN:
            skipped.append({"row": n, "reason": f"over {MAX_LEN} characters"})
            continue
        key = re.sub(r"\W+", " ", q.lower()).strip()
        if key in seen:
            skipped.append({"row": n, "reason": f"repeats row {seen[key]}"})
            continue
        if len(quotes) == MAX_QUOTES:
            skipped.append({"row": n, "reason": f"past the {MAX_QUOTES}-quote limit"})
            continue
        seen[key] = n
        authors += bool(a)
        quotes.append(f"{q} — {a}" if a else q)
    return {"quotes": quotes, "skipped": skipped, "authors": authors, "header": header}
