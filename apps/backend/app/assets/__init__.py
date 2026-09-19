"""Asset pipeline (PRD §16-18, §64): metadata and thumbnails first, score, cool down repeats, download only the winner."""
import asyncio
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from itertools import groupby

from PIL import Image

from app import config, settings, visual
from app.assets.providers import Candidate, VisualProvider, get_providers
from app.database import connect
from app.errors import UserError

SIMILAR_BITS = 10       # dHash bits that may differ before two assets count as "visually similar"
MIN_HEIGHT = 720        # usable portrait footage/photos for 1080x1920 output
VIDEO_MIN_S, VIDEO_MAX_S = 4, 90
SEARCH_LIMIT = 8        # candidates per provider per query; thumbs only, full download happens for the winner


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

async def _search_all(providers: list[VisualProvider], query: str, wanted: str) -> list[Candidate]:
    async def one(p: VisualProvider):
        return await (p.search_videos(query, SEARCH_LIMIT) if wanted == "video" else p.search_images(query, SEARCH_LIMIT))

    found = await asyncio.gather(*(one(p) for p in providers), return_exceptions=True)
    out: list[Candidate] = []
    for res in found:
        if isinstance(res, UserError):
            raise res  # auth / rate-limit problems deserve to stop the run, not quietly empty one piece
        if isinstance(res, BaseException):
            raise UserError("Visual search failed unexpectedly.", repr(res))
        out.extend(res)
    return out


async def _pick(providers: list[VisualProvider], query: str, wanted: str,
                ever: dict, recent: list[dict], weights: dict[str, float]) -> tuple[Candidate | None, dict]:
    """Best eligible candidate for one query, with its freshly fetched thumbnail if it is new. None if nothing qualifies.

    Fallback when this query's pool is exhausted (PRD §18): the least-used suitable asset, oldest use first.
    """
    candidates = sorted((c for c in await _search_all(providers, query, wanted) if suitable(c)),
                        key=lambda c: c.provider)  # stable: keeps each provider's relevance order
    best: tuple[float, Candidate, dict] | None = None
    fallback: tuple[list, Candidate] | None = None
    for _, group in groupby(candidates, key=lambda c: c.provider):
        block = list(group)
        provider = next(p for p in providers if p.name == block[0].provider)
        for rank, c in enumerate(block):
            with connect() as conn:
                row = conn.execute("SELECT * FROM assets WHERE provider = ? AND provider_asset_id = ?",
                                   (c.provider, c.provider_asset_id)).fetchone()
            used = ever.get((c.provider, c.provider_asset_id), [0, None])
            phash, themes = (row["perceptual_hash"], row["themes"]) if row else ("", "[]")
            meta: dict = {}
            if row:
                try:  # already in the library: re-analyse its stored thumbnail (also backfills pre-M4 rows)
                    thumb = (config.MEDIA_DIR / row["thumb_path"]).read_bytes()
                except OSError:
                    continue
                a = visual.analyze(thumb)
            else:
                meta["thumb"] = await provider.download_thumb(c)  # metadata + thumbnails first (PRD §64)
                phash = dhash(meta["thumb"])
                a = visual.analyze(meta["thumb"])
                meta["themes"] = json.dumps(visual.themes_from_query(query))
            if used[0]:
                if fallback is None or used < fallback[0]:
                    fallback = (used, c)  # PRD §18: never reuse until the pool is exhausted; then least-used first
                continue
            if visual.quality(a) < visual.QUALITY_FLOOR:
                continue  # PRD §78: technically poor assets are never offered
            if _cooled_out(phash, json.loads(themes), recent):
                continue
            s = score(c, rank, len(block), 0, weights, a)
            if best is None or s > best[0]:
                best = (s, c, meta | {"analysis": a})
    if best:
        return best[1], best[2]
    if fallback:  # every candidate was used: the pool for this query is exhausted, fall back per PRD §18
        return fallback[1], {}
    return None, {}


async def _assign_one(brief: dict, piece: dict, providers: list[VisualProvider],
                      ever: dict, recent: list[dict], weights: dict[str, float]) -> None:
    content = piece["content"]
    wanted = content["plan"]["visual_type"]  # ponytail: video_image forces per-type asset pairs at export (M6)
    if brief["format"] in ("video", "image"):
        wanted = brief["format"]
    best = None
    for query in dict.fromkeys([content["visual"]["search_query"], content["visual"]["secondary_query"]]):
        best, meta = await _pick(providers, query, wanted, ever, recent, weights)
        if best:
            break
    if best is None:
        raise UserError(f'No usable {wanted} turned up for the visual search "{content["visual"]["search_query"]}".')

    provider = next(p for p in providers if p.name == best.provider)
    with connect() as conn:
        row = conn.execute("SELECT id, thumb_path, perceptual_hash, themes, quality_score FROM assets "
                           "WHERE provider = ? AND provider_asset_id = ?", (best.provider, best.provider_asset_id)).fetchone()
    if row:
        asset_id, phash, themes = row["id"], row["perceptual_hash"], row["themes"]
        if "analysis" not in meta:  # fallback winner: analyse its stored thumbnail instead of a new download
            meta["thumb"] = (config.MEDIA_DIR / row["thumb_path"]).read_bytes()
            meta["analysis"] = visual.analyze(meta["thumb"])
    else:
        if "analysis" not in meta:  # brand-new fallback winner: fetch its thumbnail for analysis
            meta["thumb"] = await provider.download_thumb(best)
            meta["analysis"] = visual.analyze(meta["thumb"])
    a = meta["analysis"]
    if row:
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
        phash = dhash(meta["thumb"])
        themes = meta["themes"]
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
        content["asset"] = {"id": asset_id, "provider": best.provider, "asset_type": best.asset_type}
        content["palette"] = visual.palette(a["dominant_colors"])
        conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                     (json.dumps(content, ensure_ascii=False), piece["id"]))
    _remember(best.provider, best.provider_asset_id, phash, themes, ever, recent)


def _store(rel: str, data: bytes) -> None:
    path = config.MEDIA_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


async def _assign_all(brief: dict, pieces: list[dict], report) -> None:
    """Find and download one asset per piece. Written pieces are never lost to a visual failure: it lands in the content."""
    providers = get_providers()
    n = len(pieces)
    if not providers:
        report("Skipped visuals: add a Pexels or Unsplash key in Settings", (2 * n) / (2 * n + 1))
        return
    s = settings.get()
    ever, recent = _usage_state(s["asset_cooldown_days"])
    for i, piece in enumerate(pieces, 1):
        report(f"Finding visual {i} of {n}", (n + i) / (2 * n + 1))
        try:
            await _assign_one(brief, piece, providers, ever, recent, s["asset_weights"])
        except UserError as e:
            piece["content"]["visual_error"] = str(e)
            with connect() as conn:
                conn.execute("UPDATE content_pieces SET content = ? WHERE id = ?",
                             (json.dumps(piece["content"], ensure_ascii=False), piece["id"]))


def assign(brief: dict, pieces: list[dict], report) -> None:
    """Sync entry point from the generation pipeline (it runs on a plain job thread)."""
    asyncio.run(_assign_all(brief, pieces, report))


def list_assets() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT a.id, a.provider, a.asset_type, a.creator, a.license, a.source_url, a.width, "
                            "a.height, a.fps, a.duration, a.created_at, a.thumb_path, a.dominant_colors, "
                            "a.brightness, a.quality_score, "
                            "(SELECT count(*) FROM asset_usage u WHERE u.asset_id = a.id) AS times_used, "
                            "(SELECT max(u.created_at) FROM asset_usage u WHERE u.asset_id = a.id) AS last_used_at "
                            "FROM assets a ORDER BY a.created_at DESC, a.id DESC").fetchall()
    return [{**dict(r), "dominant_colors": json.loads(r["dominant_colors"])} for r in rows]
