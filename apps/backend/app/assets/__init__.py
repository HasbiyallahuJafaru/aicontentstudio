"""Asset pipeline (PRD §16-18, §64): metadata and thumbnails first, score, cool down repeats, download only the winner.

Nothing full-size downloads without the user (owner decision 2026-11-07): `propose` searches, fetches thumbnails only,
scores, and stores every piece's candidates with the AI's picks pre-selected (content["review"]); the user swaps
picks (`pick`), then the "visuals" job (`download_picks`) downloads exactly those and gives the project one palette."""
import asyncio
import hashlib
import time
import io
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from itertools import groupby

from PIL import Image

from app import config, settings, visual
from app.assets.providers import Candidate, CommonsProvider, VisualProvider, get_providers
from app.database import connect
from app.errors import UserError

log = logging.getLogger(__name__)

SIMILAR_BITS = 10       # dHash bits that may differ before two assets count as "visually similar"
MIN_HEIGHT = 720        # usable portrait footage/photos for 1080x1920 output
VIDEO_MIN_S, VIDEO_MAX_S = 4, 90
SEARCH_LIMIT = 6        # candidates per provider per query (one request); thumbs only, the winner downloads later
ENOUGH = 3              # usable candidates from one query that make asking the next provider unnecessary
CACHE_SECS = 6 * 3600   # a repeated search (re-roll, "find another visual") is answered from memory, not the API
PALETTE_WEIGHT = 0.35   # how much a chosen palette counts in the ranking (soft genre default: a third of that)
VOICED_CLIPS = 5        # voiced quote videos with clips behind the words (owner 2026-11-12): cut every ~2.5 s
# what each genre's clips look like when the quote's own searches run dry: slow, atmospheric, nothing literal
MOOD_CLIPS = {"hope": ["sunrise through window slow motion", "light rays forest morning", "candle flame dark"],
              "speech": ["storm clouds timelapse dark", "boxer training dark gym", "rain on window night"],
              "stoic": ["fog over mountains", "rain on stone statue", "ocean waves dark slow motion"],
              "history": ["ancient ruins fog", "old library candle", "desert dunes wind"],
              "books": ["turning pages book candle", "rain window reading", "fireplace slow"],
              "cinema": ["city lights night rain", "empty road fog", "silhouette walking sunset"]}
SHOTS = 4               # the fewest distinct visuals a video piece is cut from (one clip alone reads as a slideshow)
MAX_SHOTS = 14          # the most: one per narration sentence (2026-11-10), each a search, so it stays bounded
ARCHIVE_MIN_HEIGHT = 500  # old paintings and maps are smaller than stock and are shown whole, not cropped


# --- perceptual hashing ---------------------------------------------------------------------------------------------

def dhash(data: bytes) -> str:
    """64-bit dHash (9x8 grayscale gradient comparisons) as hex. Works on any Pillow-decodable thumbnail."""
    img = Image.open(io.BytesIO(data)).convert("L").resize((9, 8))
    px = list(img.getdata())
    bits = "".join("1" if px[y * 9 + x] > px[y * 9 + x + 1] else "0" for y in range(8) for x in range(8))
    return f"{int(bits, 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


# --- suitability and scoring (PRD §16) --------------------------------------------------------------------------------

def suitable(c: Candidate) -> bool:
    if c.provider == "commons":  # archival stills are shown whole over a blurred fill (renders._shots_for)
        return min(c.width, c.height) >= ARCHIVE_MIN_HEIGHT
    if c.width > c.height:  # outputs are portrait; landscape masters waste bandwidth and crop badly
        return False
    if c.height < MIN_HEIGHT:
        return False
    if c.asset_type == "video" and not VIDEO_MIN_S <= c.duration <= VIDEO_MAX_S:
        return False
    return True


def score(c: Candidate, rank: int, pool: int, times_used: int, weights: dict[str, float], a: dict) -> float:
    live = {
        "relevance": 1 - rank / max(pool, 1),                        # provider search order is its relevance signal
        "novelty": 1 / (1 + times_used),                             # unused beats used; used only reached via fallback
        "visual_quality": 0.5 * min(max(c.height, MIN_HEIGHT) / 1920, 1) + 0.5 * visual.quality(a),
        "composition": 1.0 if a["subject_position"] != "center" else 0.6,  # keep the middle free for the quote
        "brand": visual.no_neon(a["saturation"]),                    # PRD §24: premium and restrained, never neon
        "color": min(len(a["dominant_colors"]) / 3, 1.0),            # palette richness
        # motion arrives with M5 frame analysis; until then it scores 0 in place.
    }
    return sum(w * live.get(k, 0.0) for k, w in weights.items())


# --- cooldown state (PRD §18) -----------------------------------------------------------------------------------------

def _usage_state(cooldown_days: int) -> tuple[dict, list[dict]]:
    """(provider, id) -> (times_used, last_used) for everything ever used; phash+themes of uses inside the window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connect() as conn:
        ever = {(r["provider"], r["provider_asset_id"]): [r["n"], r["last"]]
                for r in conn.execute("SELECT a.provider, a.provider_asset_id, count(*) AS n, max(u.created_at) AS last "
                                      "FROM asset_usage u JOIN assets a ON a.id = u.asset_id GROUP BY a.id")}
        recent = [dict(r) for r in conn.execute(
            "SELECT DISTINCT a.perceptual_hash AS phash, a.themes FROM asset_usage u JOIN assets a ON a.id = u.asset_id "
            "WHERE u.created_at >= ? AND a.perceptual_hash != ''", (cutoff,))]
    return ever, recent


def _cooled_out(phash: str, themes: list[str], recent: list[dict]) -> bool:
    """True when a visually similar asset (or, once M4 fills themes in, a same-category one) was used inside the window."""
    for r in recent:
        if phash and hamming(phash, r["phash"]) <= SIMILAR_BITS:
            return True
        if themes and set(themes) & set(json.loads(r["themes"])):
            return True
    return False


def _remember(provider: str, provider_asset_id: str, phash: str, themes: str,
              ever: dict, recent: list[dict]) -> None:
    """Fold a fresh use into the in-memory state so later pieces of the same batch respect it."""
    entry = ever.setdefault((provider, provider_asset_id), [0, None])
    entry[0] += 1
    entry[1] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if phash:
        recent.append({"phash": phash, "themes": themes})


# --- selection --------------------------------------------------------------------------------------------------------

_CACHE: dict[tuple, tuple[float, list[Candidate]]] = {}
SEARCHES = {"count": 0}  # real API search requests this process made; the job reports them (owner: mind rate limits)


async def _search_all(providers: list[VisualProvider], query: str, wanted: str, palette: str = "") -> list[Candidate]:
    """Providers in order (Pexels first), one request each, stopping once a provider gave ENOUGH usable results.
    Repeats come from a short-lived cache. `palette` filters photos at the source; videos cannot be filtered."""
    out: list[Candidate] = []
    for p in providers:
        color = visual.PALETTES.get(palette, {}).get(p.name) if wanted == "image" else None
        key = (p.name, " ".join(query.lower().split()), wanted, color)
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECS:
            res = hit[1]
        else:
            try:
                if wanted == "video":
                    res = await p.search_videos(query, SEARCH_LIMIT)
                else:
                    res = await (p.search_images(query, SEARCH_LIMIT, color) if color
                                 else p.search_images(query, SEARCH_LIMIT))
            except UserError:
                raise  # auth / rate-limit problems deserve to stop the run, not quietly empty one piece
            except Exception as e:  # noqa: BLE001
                raise UserError("Visual search failed unexpectedly.", repr(e)) from e
            SEARCHES["count"] += 1
            _CACHE[key] = (time.monotonic(), res)
        out.extend(res)
        if sum(1 for c in out if suitable(c)) >= ENOUGH:
            break
    return out


def _archival(content: dict) -> set[str]:
    """Shot queries meant for Wikimedia Commons (documentaries' real portraits, maps, artefacts)."""
    return {s["query"] for s in content["visual"].get("shots") or [] if s.get("role") == "archival"}


def _queries(content: dict) -> list[str]:
    """This piece's shot queries. Pieces written before the shot list fall back to their two flat queries."""
    shots = [s["query"] for s in content["visual"].get("shots") or []]
    flat = [content["visual"]["search_query"], content["visual"].get("secondary_query", "")]
    return list(dict.fromkeys(q for q in shots + flat if q))


OLD_SMALL = 1600  # long edge (px) below which a stored Pexels photo predates the full-size download (2026-11-12)


async def _sharpen_old(asset_id: str, provider: VisualProvider) -> None:
    """A library Pexels photo saved at the old ~1300 px preview size is fetched again at full size when it is reused,
    so reusing the library never brings back soft renders. Best effort: on any failure the stored file is used."""
    if provider.name != "pexels":
        return
    with connect() as conn:
        a = conn.execute("SELECT asset_type, provider_asset_id, local_path FROM assets WHERE id = ?",
                         (asset_id,)).fetchone()
    if a is None or a["asset_type"] != "image":
        return
    path = config.MEDIA_DIR / a["local_path"]
    try:
        with Image.open(path) as im:
            if max(im.size) >= OLD_SMALL:
                return
        data = await provider.download(await provider.by_id(a["provider_asset_id"], "image"))
        Image.open(io.BytesIO(data)).verify()  # never replace a good file with a broken one
        _store(a["local_path"], data)
    except (OSError, UserError, ValueError) as e:
        log.info("kept the stored copy of %s: %r", asset_id, e)


async def _take(best: Candidate, meta: dict, piece: dict, providers: list[VisualProvider], seen: list[str],
                ever: dict, recent: list[dict]) -> dict | None:
    """Store one chosen candidate (downloading it only if it is new) and return its content entry. None when it
    looks like a shot this piece already has - checked before the full download, so a duplicate costs nothing."""
    provider = next((p for p in providers if p.name == best.provider), None) or CommonsProvider()
    with connect() as conn:
        row = conn.execute("SELECT id, thumb_path, perceptual_hash, themes, quality_score FROM assets "
                           "WHERE provider = ? AND provider_asset_id = ?",
                           (best.provider, best.provider_asset_id)).fetchone()
    if row:
        phash, themes = row["perceptual_hash"], row["themes"]
        if "analysis" not in meta:  # fallback winner: analyse its stored thumbnail instead of a new download
            meta["thumb"] = (config.MEDIA_DIR / row["thumb_path"]).read_bytes()
            meta["analysis"] = visual.analyze(meta["thumb"])
    else:
        if "analysis" not in meta:  # brand-new fallback winner: fetch its thumbnail for analysis
            meta["thumb"] = await provider.download_thumb(best)
            meta["analysis"] = visual.analyze(meta["thumb"])
        phash, themes = dhash(meta["thumb"]), meta.get("themes", "[]")
    if any(hamming(phash, s) <= SIMILAR_BITS for s in seen):
        return None  # cutting back to a near-identical frame reads as a stutter, not as an edit
    a = meta["analysis"]
    if row:
        asset_id = row["id"]
        await _sharpen_old(row["id"], provider)
        if row["quality_score"] is None:  # backfill the analysis columns on pre-M4 rows
            with connect() as conn:
                conn.execute("UPDATE assets SET brightness = ?, saturation = ?, contrast = ?, dominant_colors = ?, "
                             "subject_position = ?, visual_complexity = ?, temperature = ?, quality_score = ?, "
                             "themes = CASE WHEN themes = '[]' THEN ? ELSE themes END WHERE id = ?",
                             (a["brightness"], a["saturation"], a["contrast"], json.dumps(a["dominant_colors"]),
                              a["subject_position"], a["visual_complexity"], a["temperature"], visual.quality(a),
                              meta.get("themes", "[]"), asset_id))
    else:
        asset_id = uuid.uuid4().hex[:12]
        data = await provider.download(best)
        aext = "mp4" if best.asset_type == "video" else "jpg"  # ponytail: providers only serve mp4/jpeg today
        text = Image.open(io.BytesIO(meta["thumb"])).format.lower()  # thumbs arrive as jpeg/bmp/webp; trust the bytes
        _store(f"assets/{asset_id}.{aext}", data)
        _store(f"thumbs/{asset_id}.{text}", meta["thumb"])
        with connect() as conn:
            conn.execute(
                "INSERT INTO assets (id, provider, provider_asset_id, asset_type, creator, license, source_url, "
                "local_path, thumb_path, width, height, fps, duration, hash, perceptual_hash, brightness, saturation, "
                "contrast, dominant_colors, subject_position, visual_complexity, temperature, quality_score, themes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (asset_id, best.provider, best.provider_asset_id, best.asset_type, best.creator, provider.LICENSE,
                 best.source_url, f"assets/{asset_id}.{aext}", f"thumbs/{asset_id}.{text}", best.width, best.height,
                 best.fps, best.duration, hashlib.sha256(data).hexdigest(), phash, a["brightness"], a["saturation"],
                 a["contrast"], json.dumps(a["dominant_colors"]), a["subject_position"], a["visual_complexity"],
                 a["temperature"], visual.quality(a), themes))
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO asset_usage (asset_id, piece_id) VALUES (?, ?)", (asset_id, piece["id"]))
    _remember(best.provider, best.provider_asset_id, phash, themes, ever, recent)
    seen.append(phash)
    return {"id": asset_id, "provider": best.provider, "asset_type": best.asset_type, "analysis": a}


def _store(rel: str, data: bytes) -> None:
    path = config.MEDIA_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# --- review: propose candidates, the user picks, then download ---------------------------------------------------------

def _wanted(brief: dict, content: dict) -> str:
    wanted = content["plan"]["visual_type"]  # ponytail: video_image forces per-type asset pairs at export (M6)
    if brief["format"] == "image_voiced":  # the picture read aloud: a photo, or clips behind the words (2026-11-12)
        return "video" if brief.get("backdrop") == "clips" else "image"
    return brief["format"] if brief["format"] in ("video", "image") else wanted


async def _options(providers: list[VisualProvider], query: str, wanted: str, ever: dict, recent: list[dict],
                   weights: dict[str, float], known: dict[str, dict], palette: str = "", soft: str = "") -> list[dict]:
    """Every suitable candidate for one query, thumbnail stored for the review screen, scored. Technically poor
    ones are never offered (PRD §78); used or recently similar ones are offered but flagged, and never pre-picked.
    `known` (key -> option) holds what earlier queries already offered: those only gain this query, no refetch."""
    out = []
    candidates = sorted((c for c in await _search_all(providers, query, wanted, palette) if suitable(c)),
                        key=lambda c: c.provider)
    for _, group in groupby(candidates, key=lambda c: c.provider):
        block = list(group)
        provider = next(p for p in providers if p.name == block[0].provider)
        for rank, c in enumerate(block):
            key = f"{c.provider}:{c.provider_asset_id}"
            if key in known:
                if query not in known[key]["queries"]:
                    known[key]["queries"].append(query)
                continue
            with connect() as conn:
                row = conn.execute("SELECT * FROM assets WHERE provider = ? AND provider_asset_id = ?",
                                   (c.provider, c.provider_asset_id)).fetchone()
            if row:  # already in the library: its stored thumbnail is the preview, nothing to fetch
                thumb_rel, phash, themes = row["thumb_path"], row["perceptual_hash"], row["themes"]
                try:
                    thumb = (config.MEDIA_DIR / thumb_rel).read_bytes()
                except OSError:
                    continue
            else:
                thumb = await provider.download_thumb(c)  # thumbnails only (PRD §64): the full file waits for the user
                ext = Image.open(io.BytesIO(thumb)).format.lower()
                thumb_rel = f"candidates/{c.provider}-{c.provider_asset_id}.{ext}"
                _store(thumb_rel, thumb)
                phash, themes = dhash(thumb), json.dumps(visual.themes_from_query(query))
            a = visual.analyze(thumb)
            if visual.quality(a) < visual.QUALITY_FLOOR:
                continue
            used = ever.get((c.provider, c.provider_asset_id), [0, None])
            # the category cooldown applies to library assets (their stored themes); a brand-new candidate is judged
            # by look alone, as before review existed
            cool_themes = json.loads(themes) if row else []
            note = "used" if used[0] else "similar" if _cooled_out(phash, cool_themes, recent) else None
            # the palette counts in the ranking: fully when the user chose one, softly for the genre's usual look
            look = (PALETTE_WEIGHT * visual.palette_match(a, palette) if palette
                    else PALETTE_WEIGHT / 3 * visual.palette_match(a, soft))
            known[key] = {"key": key, "queries": [query], "candidate": c.model_dump(),
                        "thumb": thumb_rel, "phash": phash, "themes": themes, "analysis": a, "note": note,
                        "used": used[0], "score": round(score(c, rank, len(block), 0, weights, a) + look, 4)}
            out.append(known[key])
    return out


def _prepick(options: list[dict], queries: list[str], want: int, rounds: int = 1) -> list[str]:
    """The AI's choice, the same rules as before review existed: per planned shot the best fresh candidate, never
    a near-duplicate of one already picked; a query with no fresh candidate falls back to its least-used one."""
    picked: list[dict] = []
    # `rounds` > 1 goes over the queries again (voiced quote clips: two searches can still fill five clips)
    for q in [q for _ in range(rounds) for q in queries]:
        if len(picked) >= want:
            break
        pool = [o for o in options if q in o["queries"] and o not in picked
                and not any(hamming(o["phash"], p["phash"]) <= SIMILAR_BITS for p in picked)]
        fresh = [o for o in pool if o["note"] is None]
        # an exhausted pool falls back to its least-used footage (PRD §18); footage that merely looks like something
        # used recently is shown to the user but never chosen for them
        used = [o for o in pool if o["note"] == "used"]
        best = max(fresh, key=lambda o: o["score"]) if fresh else min(used, key=lambda o: o["used"], default=None)
        if best:
            picked.append(best)
    return [o["key"] for o in picked]


async def _propose_one(brief: dict, piece: dict, providers: list[VisualProvider], ever: dict, recent: list[dict],
                       weights: dict[str, float]) -> None:
    content = piece["content"]
    wanted = _wanted(brief, content)
    queries = _queries(content)
    archival = _archival(content)
    # a video gets one visual per planned shot (one per sentence), never fewer than SHOTS
    want = min(max(len(content["visual"].get("shots") or []), SHOTS), MAX_SHOTS) if wanted == "video" else 1
    if brief["format"] == "image_voiced" and wanted == "video":  # clips behind a quote: its searches, then the mood's
        want = VOICED_CLIPS
        queries += [q for q in MOOD_CLIPS.get(brief.get("tone", ""), []) if q not in queries]
    rounds = want if brief["format"] == "image_voiced" else 1
    commons = [CommonsProvider()] if archival else []
    palette = brief.get("palette", "auto")
    palette, soft = (palette, "") if palette in visual.PALETTES else ("", visual.GENRE_PALETTE.get(brief["tone"], ""))
    options: list[dict] = []
    known: dict[str, dict] = {}  # one asset can answer two shot queries: offered once, fetched once
    searched: list[str] = []
    for q in queries:  # lazily: stop as soon as every needed shot has a fresh pick (an image usually needs one query)
        if q in archival:  # a real portrait / map / artefact: Commons stills, never stock
            options += await _options(commons, q, "image", ever, recent, weights, known)
        else:
            options += await _options(providers, q, wanted, ever, recent, weights, known, palette, soft)
        searched.append(q)
        picks = _prepick(options, searched, want, rounds)
        if len(picks) >= want and all(o["note"] is None for o in options if o["key"] in picks):
            break
    if not options:
        raise UserError(f'No usable {wanted} turned up for the visual search "{content["visual"]["search_query"]}".')
    picked = _prepick(options, queries, want, rounds)
    for o in options:  # later pieces of this batch see these pre-picks as taken, as if already downloaded (PRD §18)
        if o["key"] in picked:
            c = o["candidate"]
            _remember(c["provider"], c["provider_asset_id"], o["phash"], o["themes"], ever, recent)
    content["review"] = {"want": want, "type": wanted, "options": options, "picked": picked}
    content.pop("visual_error", None)
    with connect() as conn:
        conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                     (json.dumps(content, ensure_ascii=False), piece["id"]))


async def _propose_all(brief: dict, pieces: list[dict], report) -> None:
    """Candidates for every piece. Written pieces are never lost to a visual failure: it lands in the content."""
    providers = get_providers()
    n = len(pieces)
    if not providers:
        report("Skipped visuals: add a Pexels or Unsplash key in Settings", (2 * n) / (2 * n + 1))
        return
    s = settings.get()
    ever, recent = _usage_state(s["asset_cooldown_days"])
    start = SEARCHES["count"]
    for i, piece in enumerate(pieces, 1):
        used = SEARCHES["count"] - start
        report(f"Finding footage options {i} of {n} ({used} stock {'search' if used == 1 else 'searches'} so far)",
               (n + i) / (2 * n + 1))
        try:
            await _propose_one(brief, piece, providers, ever, recent, s["asset_weights"])
        except UserError as e:
            piece["content"]["visual_error"] = str(e)
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                             (json.dumps(piece["content"], ensure_ascii=False), piece["id"]))


def propose(brief: dict, pieces: list[dict], report) -> None:
    """Sync entry point from the generation pipeline (it runs on a plain job thread)."""
    asyncio.run(_propose_all(brief, pieces, report))


def pick(piece_id: str, keys: list[str]) -> dict:
    """Save the user's footage choice for one piece (in play order). Saved at once, so it survives a restart."""
    from app import jobs
    with connect() as conn:
        row = conn.execute("SELECT project_id, content FROM content_pieces WHERE id = ?", (piece_id,)).fetchone()
    if row is None:
        raise UserError("This piece no longer exists.", f"piece id {piece_id}")
    jobs.ensure_idle(row["project_id"], "changing its footage")  # the download job reads these picks
    content = json.loads(row["content"])
    review = content.get("review")
    if not review:
        raise UserError("This piece has no footage waiting to be picked.")
    offered = {o["key"] for o in review["options"]}
    keys = list(dict.fromkeys(k for k in keys if k in offered))[: review["want"]]
    if not keys:
        raise UserError("Pick at least one shot for this piece.")
    review["picked"] = keys
    with connect() as conn:
        conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?", (json.dumps(content, ensure_ascii=False), piece_id))
    return {"picked": keys}


LINK = re.compile(r"https?://(?:www\.)?(pexels|unsplash)\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(photo|photos|video)/([^/?#]+)",
                  re.I)


def add_links(piece_id: str, urls: str) -> dict:
    """The user's own picks (owner 2026-11-12): Pexels photo or video pages and Unsplash photo pages, several at
    once (commas, spaces or new lines between them), added to the piece's options and picked in the order pasted,
    ahead of the studio's own picks. A piece that can show several visuals grows to hold them all (up to
    MAX_SHOTS); a single picture post keeps one. Only thumbnails are fetched now; full files download with the other
    picks. A link that can't be used is skipped with a reason, the rest still land."""
    from app import jobs, projects
    found = [u for u in re.split(r"[\s,]+", urls.strip()) if u]
    if not found:
        raise UserError("Paste one or more Pexels or Unsplash links.")
    with connect() as conn:
        row = conn.execute("SELECT project_id, content FROM content_pieces WHERE id = ?", (piece_id,)).fetchone()
    if row is None:
        raise UserError("This piece no longer exists.", f"piece id {piece_id}")
    jobs.ensure_idle(row["project_id"], "changing its footage")
    brief = projects.get(row["project_id"])["brief"]
    content = json.loads(row["content"])
    review = content.get("review")
    if not review:
        raise UserError("This piece has no footage waiting to be picked.")
    providers = {p.name: p for p in get_providers()}

    async def one(url: str) -> dict:
        m = LINK.match(url)
        if not m:
            raise UserError("Not a Pexels photo or video link, or an Unsplash photo link.")
        site, kind, slug = m[1].lower(), m[2].lower(), m[3]
        provider = providers.get(site)
        if provider is None:
            raise UserError(f"Add your {site.title()} key in Settings to use {site.title()} links.")
        c = await provider.by_id(slug, "video" if kind == "video" else "image")
        if c.asset_type == "video" and review["type"] == "image":
            raise UserError("A video can't go behind a photo post. Choose Moving clips when you create the project.")
        key = f"{c.provider}:{c.provider_asset_id}"
        known = next((o for o in review["options"] if o["key"] == key), None)
        if known:
            return known
        thumb = await provider.download_thumb(c)
        thumb_rel = f"candidates/{c.provider}-{c.provider_asset_id}.{Image.open(io.BytesIO(thumb)).format.lower()}"
        _store(thumb_rel, thumb)
        return {"key": key, "candidate": c.model_dump(), "thumb": thumb_rel, "phash": dhash(thumb),
                "themes": json.dumps([]), "queries": ["your link"], "score": 1.0, "note": None, "used": 0,
                "analysis": visual.analyze(thumb)}

    async def everything():
        return await asyncio.gather(*(one(u) for u in found), return_exceptions=True)

    added, skipped = [], []
    for url, got in zip(found, asyncio.run(everything())):
        if isinstance(got, UserError):
            skipped.append({"url": url, "reason": str(got)})
        elif isinstance(got, Exception):
            log.warning("link %s failed: %r", url, got)
            skipped.append({"url": url, "reason": "Couldn't fetch this one. Check the link and try again."})
        elif got["key"] not in [o["key"] for o in added]:
            added.append(got)
    if added:
        _use(piece_id, content, review, brief, added)
    elif len(skipped) == 1:
        raise UserError(skipped[0]["reason"], skipped[0]["url"])
    return {"added": added, "picked": review["picked"], "want": review["want"], "skipped": skipped}


def _use(piece_id: str, content: dict, review: dict, brief: dict, added: list[dict]) -> None:
    """The user's own picks (pasted links, library items) join the piece's options and play first, in the order
    chosen; the piece grows to hold them (up to MAX_SHOTS; a single picture post keeps one). Saved at once."""
    keys = [o["key"] for o in added]
    review["options"] = added + [o for o in review["options"] if o["key"] not in keys]
    linked = list(dict.fromkeys(keys + review.get("linked", [])))  # this choice first, earlier ones after
    review["linked"] = linked
    review.setdefault("base_want", review["want"])
    single = brief["format"] == "image"  # a picture post shows one photo; everything else can cut between many
    review["want"] = 1 if single else min(max(review["base_want"], len(linked)), MAX_SHOTS)
    rest = [k for k in review["picked"] if k not in linked]
    review["picked"] = (linked + rest)[: review["want"]]
    with connect() as conn:
        conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                     (json.dumps(content, ensure_ascii=False), piece_id))


def add_from_library(piece_id: str, asset_ids: list[str]) -> dict:
    """Reuse photos and clips already downloaded (owner 2026-11-12): library items added to the piece and picked,
    in the order chosen. Nothing is fetched; the stored file is used (`_take` finds the library row). A video can't
    go behind a photo post, so those are skipped with a reason, like a pasted link."""
    from app import jobs, projects
    ids = list(dict.fromkeys(a for a in asset_ids if a))
    if not ids:
        raise UserError("Choose at least one photo or clip from your library.")
    with connect() as conn:
        row = conn.execute("SELECT project_id, content FROM content_pieces WHERE id = ?", (piece_id,)).fetchone()
        assets = {r["id"]: dict(r) for r in conn.execute(
            f"SELECT * FROM assets WHERE id IN ({','.join('?' * len(ids))})", ids)}
    if row is None:
        raise UserError("This piece no longer exists.", f"piece id {piece_id}")
    jobs.ensure_idle(row["project_id"], "changing its footage")
    brief = projects.get(row["project_id"])["brief"]
    content = json.loads(row["content"])
    review = content.get("review")
    if not review:
        raise UserError("This piece has no footage waiting to be picked.")
    added, skipped = [], []
    for aid in ids:
        a = assets.get(aid)
        if a is None:
            skipped.append({"id": aid, "reason": "That item is no longer in your library."})
            continue
        if a["asset_type"] == "video" and review["type"] == "image":
            skipped.append({"id": aid, "reason": "A video can't go behind a photo post."})
            continue
        c = Candidate(provider=a["provider"], provider_asset_id=a["provider_asset_id"], asset_type=a["asset_type"],
                      creator=a["creator"] or "", source_url=a["source_url"] or "", download_url="",
                      thumb_url="", width=a["width"] or 0, height=a["height"] or 0, fps=a["fps"] or 0,
                      duration=a["duration"] or 0)
        analysis = {"brightness": a["brightness"], "saturation": a["saturation"], "contrast": a["contrast"],
                    "dominant_colors": json.loads(a["dominant_colors"] or "[]"),
                    "subject_position": a["subject_position"], "visual_complexity": a["visual_complexity"],
                    "temperature": a["temperature"]}
        if analysis["brightness"] is None:  # a pre-analysis row: read its stored thumbnail now
            analysis = visual.analyze((config.MEDIA_DIR / a["thumb_path"]).read_bytes())
        added.append({"key": f"{c.provider}:{c.provider_asset_id}", "candidate": c.model_dump(),
                      "thumb": a["thumb_path"], "phash": a["perceptual_hash"], "themes": a["themes"] or "[]",
                      "queries": ["your library"], "score": 1.0, "note": None, "used": 0, "analysis": analysis})
    if added:
        _use(piece_id, content, review, brief, added)
    elif skipped:
        raise UserError(skipped[0]["reason"], skipped[0]["id"])
    return {"added": added, "picked": review["picked"], "want": review["want"], "skipped": skipped}


def _drop_previews(thumbs: set[str]) -> None:
    """Delete review previews nobody still needs: the library owns its own thumbnails, and a preview another
    piece (any project) is still choosing from stays until that review is done too."""
    with connect() as conn:
        pending = [json.loads(r[0]).get("review") for r in
                   conn.execute("SELECT content FROM content_pieces WHERE content LIKE '%\"review\"%'")]
    keep = {o["thumb"] for rv in pending if rv for o in rv["options"]}
    for t in thumbs - keep:
        if t.startswith("candidates/"):
            (config.MEDIA_DIR / t).unlink(missing_ok=True)


def _project_palette(project_id: str, pending: set[str]) -> dict | None:
    """One palette for the whole project (owner decision): pieces confirmed earlier lend the project's palette to
    the new ones; otherwise it is built from every hero shot's colours across the batch."""
    with connect() as conn:
        rows = conn.execute("SELECT id, content FROM content_pieces WHERE project_id = ? ORDER BY idx",
                            (project_id,)).fetchall()
        settled = [json.loads(r["content"]).get("palette") for r in rows if r["id"] not in pending]
        if any(settled):
            return next(p for p in settled if p)
        heroes = [(json.loads(r["content"]).get("asset") or {}).get("id") for r in rows]
        found = [conn.execute("SELECT dominant_colors FROM assets WHERE id = ?", (h,)).fetchone() for h in heroes if h]
    colors = [json.loads(f["dominant_colors"]) for f in found if f]
    # interleave: each piece's strongest colour first, so no single piece decides the batch's look
    mixed = [c[i] for i in range(max(map(len, colors), default=0)) for c in colors if i < len(c)]
    return visual.palette(mixed) if mixed else None


async def _download_all(project_id: str, report) -> None:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM content_pieces WHERE project_id = ? ORDER BY idx", (project_id,)).fetchall()
    pieces = [{**dict(r), "content": json.loads(r["content"])} for r in rows]
    pieces = [p for p in pieces if p["content"].get("review")]
    if not pieces:
        raise UserError("There is no footage waiting to be downloaded in this project.")
    unpicked = [str(p["idx"]) for p in pieces if not p["content"]["review"]["picked"]]
    if unpicked:  # checked before any download, so a half-confirmed project never half-downloads
        raise UserError(f"Pick footage for piece {', '.join(unpicked)} first.")
    providers = get_providers()
    if not providers:
        raise UserError("Add a Pexels or Unsplash key in Settings to download footage.")
    s = settings.get()
    ever, recent = _usage_state(s["asset_cooldown_days"])
    previews = [p["content"]["review"]["options"] for p in pieces]
    for i, piece in enumerate(pieces, 1):
        report(f"Downloading footage {i} of {len(pieces)}", (i - 1) / len(pieces))
        content, review = piece["content"], piece["content"]["review"]
        by_key = {o["key"]: o for o in review["options"]}
        picked, seen = [], []
        for key in review["picked"]:
            o = by_key[key]
            meta = {"thumb": (config.MEDIA_DIR / o["thumb"]).read_bytes(), "analysis": o["analysis"],
                    "themes": o["themes"]}
            entry = await _take(Candidate(**o["candidate"]), meta, piece, providers, seen, ever, recent)
            if entry:
                picked.append(entry)
        if not picked:
            raise UserError(f"None of the footage picked for piece {piece['idx']} could be used.")
        content["assets"] = [{k: v for k, v in e.items() if k != "analysis"} for e in picked]
        content["asset"] = content["assets"][0]
        del content["review"]
        with connect() as conn:  # new footage makes any earlier render of this piece stale
            for r in conn.execute("SELECT local_path FROM renders WHERE piece_id = ?", (piece["id"],)).fetchall():
                (config.MEDIA_DIR / r["local_path"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM renders WHERE piece_id = ?", (piece["id"],))
            conn.execute("UPDATE content_pieces SET status = 'written', content = ? WHERE id = ?",
                         (json.dumps(content, ensure_ascii=False), piece["id"]))
    _drop_previews({o["thumb"] for opts in previews for o in opts})
    palette = _project_palette(project_id, {p["id"] for p in pieces})
    if palette:
        with connect() as conn:
            for piece in pieces:
                c = json.loads(conn.execute("SELECT content FROM content_pieces WHERE id = ?",
                                            (piece["id"],)).fetchone()[0])
                c["palette"] = palette
                conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                             (json.dumps(c, ensure_ascii=False), piece["id"]))
    report("Footage ready", 1.0)


def download_picks(project_id: str, report) -> None:
    """The "visuals" job: download exactly the footage the user confirmed, then one palette for the project."""
    asyncio.run(_download_all(project_id, report))


def delete_asset(asset_id: str) -> dict:
    """Delete one library asset and its files. Finished renders keep their pixels; a piece that used it drops that
    shot, and a piece left with no footage is told to find another visual (it is never silently broken)."""
    from app import jobs  # jobs imports assets: resolve at call time
    with connect() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise UserError("This asset no longer exists.", f"asset id {asset_id}")
        users = conn.execute("SELECT c.id, c.project_id, c.content FROM content_pieces c JOIN asset_usage u "
                             "ON u.piece_id = c.id WHERE u.asset_id = ?", (asset_id,)).fetchall()
    for u in users:
        jobs.ensure_idle(u["project_id"])
    with connect() as conn:
        for u in users:
            c = json.loads(u["content"])
            c["assets"] = [a for a in c.get("assets") or [] if a["id"] != asset_id]
            if c["assets"]:
                c["asset"] = c["assets"][0]
            else:
                c.pop("assets", None), c.pop("asset", None)
                c["visual_error"] = "Its footage was deleted from the library. Find another visual."
            conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?", (json.dumps(c, ensure_ascii=False), u["id"]))
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))  # usage rows cascade
    for rel in (row["local_path"], row["thumb_path"]):
        if rel:
            (config.MEDIA_DIR / rel).unlink(missing_ok=True)
    return {"deleted": asset_id}


def list_assets() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT a.id, a.provider, a.asset_type, a.creator, a.license, a.source_url, a.width, "
                            "a.height, a.fps, a.duration, a.created_at, a.thumb_path, a.dominant_colors, "
                            "a.brightness, a.quality_score, "
                            "(SELECT count(*) FROM asset_usage u WHERE u.asset_id = a.id) AS times_used, "
                            "(SELECT max(u.created_at) FROM asset_usage u WHERE u.asset_id = a.id) AS last_used_at "
                            "FROM assets a ORDER BY a.created_at DESC, a.id DESC").fetchall()
    return [{**dict(r), "dominant_colors": json.loads(r["dominant_colors"])} for r in rows]
