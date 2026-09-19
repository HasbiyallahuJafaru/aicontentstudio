# Handover

Last updated: 2026-09-19. Read this first in a new chat, then `.claude/CLAUDE.md` rules. Update it after every phase.

## Where things stand

| PRD milestone | State |
|---|---|
| Phase 0 research | Done: `DECISIONS.md` |
| Milestone 1: Electron shell, React, Python process, SQLite, Settings, basic project creation | Done, verified |
| Milestone 2: DeepSeek, content schemas, batch generation, persistence of pieces | Done, verified with a fake DeepSeek (never called the real API yet) |
| UI redesign to the user's reference (warm glass, icon rail, Sora/Geist, pill controls) | Done, one screenshot review round |
| **Milestone 3**: Pexels/Unsplash providers, asset pipeline (scoring, dedup, cooldown), Library page | **Done, verified with fake providers** (never called the real APIs yet) |
| M4 visual analysis, palette · M5 TTS, audio, FFmpeg renderers · M6 preview, regeneration, queue, export · M7 refinement · packaging | Not started |

Git: `main` on https://github.com/HasbiyallahuJafaru/aicontentstudio. Milestone 1 = b53f78b, Milestone 2 + redesign = cba6239.
Commit/push only when the user asks.

## What exists

**Backend** (`apps/backend`, venv `.venv`, deps: pydantic, httpx, Pillow)
- stdio JSON-lines RPC (`app/rpc.py`, method table `METHODS`); `app/events.py` writes responses/events to stdout.
  Events: `backend.ready`, `job.started|progress|completed|failed|cancelled` (payload = job row).
- Methods: `app.info`, `app.stats`, `settings.get|update`, `projects.create|list|get|delete`, `pieces.list`,
  `pieces.recent`, `assets.list`, `jobs.start|cancel|latest`, `secrets.load` (Electron main only).
- DB migrations: `001_init` (projects, settings), `002_content` (content_pieces, generation_jobs),
  `003_assets` (assets, asset_usage; M4 analysis columns are placeholders).
- `app/creative/`: `schemas.py` (BatchPlan with distinct angles/subjects, PieceContent = quote/narration/visual/design
  hints/metadata; quote author must be null), `prompts.py` (provider-neutral messages), `model.py` (`CreativeModel`
  interface + `DeepSeekModel`, `get_model()` raises "Add your DeepSeek API key…" if none).
- `app/content.py`: pipeline = plan batch (avoiding recent quotes + narration openings) → write each piece →
  `assets.assign` for one visual per piece. Quote similarity via difflib ≥0.75 vs history+batch, up to 3 attempts
  then the piece is stored `failed` with the reason. Regenerating a project replaces its pieces (and their usage rows).
  Progress counts 2n+1 real steps: plan + write i + find visual i. Job completes with stage "Done".
- `app/assets/`: `providers.py` (`VisualProvider` = search_images/search_videos/download/download_thumb;
  `PexelsProvider` photos+videos picking the portrait mp4 closest to 1080×1920, `UnsplashProvider` photos only,
  downloads via `links.download_location` = required tracking ping; `ACS_PEXELS_URL`/`ACS_UNSPLASH_URL` env override
  base URLs for tests) and `__init__.py` (pipeline): metadata + thumbnails first (PRD §64), suitability filter
  (portrait, ≥720px, 4–90 s), scoring with configurable weights (relevance by search rank, resolution proxy,
  novelty; M4/M5 components score 0 in place), exact dedup by `(provider, provider_asset_id)` UNIQUE + own dHash
  (9×8, 64-bit; hamming ≤10 = similar), cooldown: same asset never reused until a query's pool is exhausted
  (then least-used LRU), similar/category within `asset_cooldown_days` excluded. Winner only is downloaded to
  `media/assets/<id>.<ext>` + thumbnail to `media/thumbs/<id>.<ext>` (thumb extension sniffed from the bytes).
  Per-piece failures (no candidates, download error) are stored as `visual_error` in the piece content and never
  lose written pieces; no keys → the phase is skipped with an honest stage message.
- `app/jobs.py`: one thread per job, cancel between steps, `recover()` on startup marks interrupted jobs failed.
  Project status: draft → generating → ready | failed.
- Tests: `python -m unittest` = 36 tests (fake model/providers; `httpx.MockTransport` for DeepSeek repair/retry/
  401/empty/wrong count and Pexels/Unsplash parsing, video-file picking, auth errors, download ping).

**Desktop** (`apps/desktop`)
- Screens: Studio dashboard, Create (glass brief form + live batch preview), Projects list, Project page (Generate /
  Generate again with Ctrl+Enter, live stage + progress + Cancel, pieces with quote, narration, visual query, delivery,
  per-piece `visual_error` shown in red under Visual, collapsible captions/metadata, failed-piece reasons, delete),
  Settings (keys, AI, content defaults incl. Asset cooldown days, storage), and Library: thumbnail grid over
  `media://`, filters (Type, Provider, Usage: All/Never used/Recently used), honest empty states, duration + 60 FPS
  badge on video tiles, usage count + last used + creator per card.
- `media://` protocol (registered privileged in `electron/main.ts`) serves `<dataDir>/media` to the sandboxed
  renderer with a path-traversal guard; CSP `img-src` includes `media:`. Chromium collapses `media:///a/b` to
  `media://a/b`, so the handler resolves host+pathname.
- Design system (`src/styles/index.css` + `glass`, `.ambient`, `.grain`; primitives in `src/components/ui.tsx`):
  warm charcoal, ember-orange accent, Sora display / Geist body, pill controls, 14px fields, 26px panels.
  `useJob()` in `src/lib/studio.ts` listens to job events; `mediaUrl(rel)` builds `media://` URLs.
- `scripts/smoke.mjs` runs the real app against a local fake DeepSeek AND a fake Pexels server (distinct striped BMP
  thumbnails so dHashes differ): set keys, save settings, create + generate 3 pieces with visuals, Library shows
  3 cards + filters work, restart, everything persisted. Screenshots → `%TEMP%/acs-smoke`.

**Verified 2026-09-19:** `npm test` from the root (36 unittest + tsc + build + smoke) passes; screenshots reviewed
(Library grid with real thumbnails, empty state, Settings, Project page).
**Not verified:** real DeepSeek call and real Pexels/Unsplash calls (need the user's keys; prompt/provider quality
unknown), Unsplash path end to end (only Pexels is faked in smoke), `npm run dev` HMR, very long strings,
video files are never decoded (only thumbnails), dominant colors / brightness / themes wait for M4, motion for M5.

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # all checks
graphify update . # refresh the code map after changes
```

## Next: Milestone 4 (visual analysis + palette)
1. First, with the user's DeepSeek key: generate one real batch, read the output, tune `prompts.py` if quotes sound
   AI-ish. (Still pending from M3 — needs the user's key; also add real Pexels/Unsplash keys and eyeball the
   Library results.)
2. M4 per PRD §22/§23: analyze chosen assets with Pillow/OpenCV (brightness, saturation, contrast, dominant colors,
   themes), fill the placeholder columns in `assets`, light up the M4 scoring components already wired in
   `assets.score()`, and use dominant colors in the palette engine.
3. Batch planner already diversifies subjects/angles; consider a `themes` seed for the category cooldown.

## Open decisions / notes
- Rail shows Dashboard, Create, Projects, Library; Queue and Exports arrive with M6.
- Platform-specific metadata adapters (PRD §69) come with export (M6); pieces currently hold one metadata set.
- Scoring weights are backend-configurable (settings `asset_weights`, PRD §16 map) but have no Settings UI fields
  yet; the user-facing knob is `asset_cooldown_days`. Add UI fields if the user wants to tune them.
- `video_image` brief format still picks one visual per piece (plan's type); per-type asset pairs arrive with
  export (M6).
- Media folder is read-only in Settings; changing it needs a move step (later).
