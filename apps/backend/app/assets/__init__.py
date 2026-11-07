"""Asset pipeline (PRD §16-18, §64): metadata and thumbnails first, score, cool down repeats, download only the winner.

Nothing full-size downloads without the user (owner decision 2026-11-07): `propose` searches, fetches thumbnails only,
scores, and stores every piece's candidates with the AI's picks pre-selected (content["review"]); the user swaps
picks (`pick`), then the "visuals" job (`download_picks`) downloads exactly those and gives the project one palette."""
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
SEARCH_LIMIT = 5        # candidates per provider per query; thumbs only, full download happens for the winner
SHOTS = 4               # distinct visuals a video piece is cut from (one clip on its own reads as a slideshow)


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


def _queries(content: dict) -> list[str]:
    """This piece's shot queries. Pieces written before the shot list fall back to their two flat queries."""
    shots = [s["query"] for s in content["visual"].get("shots") or []]
    flat = [content["visual"]["search_query"], content["visual"].get("secondary_query", "")]
    return list(dict.fromkeys(q for q in shots + flat if q))


async def _take(best: Candidate, meta: dict, piece: dict, providers: list[VisualProvider], seen: list[str],
                ever: dict, recent: list[dict]) -> dict | None:
    """Store one chosen candidate (downloading it only if it is new) and return its content entry. None when it
    looks like a shot this piece already has - checked before the full download, so a duplicate costs nothing."""
    provider = next(p for p in providers if p.name == best.provider)
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
    return brief["format"] if brief["format"] in ("video", "image") else wanted


async def _options(providers: list[VisualProvider], query: str, wanted: str, ever: dict, recent: list[dict],
                   weights: dict[str, float], known: dict[str, dict]) -> list[dict]:
    """Every suitable candidate for one query, thumbnail stored for the review screen, scored. Technically poor
    ones are never offered (PRD §78); used or recently similar ones are offered but flagged, and never pre-picked.
    `known` (key -> option) holds what earlier queries already offered: those only gain this query, no refetch."""
    out = []
    candidates = sorted((c for c in await _search_all(providers, query, wanted) if suitable(c)), key=lambda c: c.provider)
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
            known[key] = {"key": key, "queries": [query], "candidate": c.model_dump(),
                        "thumb": thumb_rel, "phash": phash, "themes": themes, "analysis": a, "note": note,
                        "used": used[0], "score": round(score(c, rank, len(block), 0, weights, a), 4)}
            out.append(known[key])
    return out


def _prepick(options: list[dict], queries: list[str], want: int) -> list[str]:
    """The AI's choice, the same rules as before review existed: per planned shot the best fresh candidate, never
    a near-duplicate of one already picked; a query with no fresh candidate falls back to its least-used one."""
    picked: list[dict] = []
    for q in queries:
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
    want = SHOTS if wanted == "video" else 1
    queries = _queries(content)
    options: list[dict] = []
    known: dict[str, dict] = {}  # one asset can answer two shot queries: offered once, fetched once
    for q in queries:
        options += await _options(providers, q, wanted, ever, recent, weights, known)
    if not options:
        raise UserError(f'No usable {wanted} turned up for the visual search "{content["visual"]["search_query"]}".')
    picked = _prepick(options, queries, want)
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
    for i, piece in enumerate(pieces, 1):
        report(f"Finding footage options {i} of {n}", (n + i) / (2 * n + 1))
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
    with connect() as conn:
        row = conn.execute("SELECT content FROM content_pieces WHERE id = ?", (piece_id,)).fetchone()
    if row is None:
        raise UserError("This piece no longer exists.", f"piece id {piece_id}")
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
