# Handover

Last updated: 2026-09-19. Read this first in a new chat, then `.claude/CLAUDE.md` rules. Update it after every phase.

## Where things stand

| PRD milestone | State |
|---|---|
| Phase 0 research | Done: `DECISIONS.md` |
| Milestone 1: Electron shell, React, Python process, SQLite, Settings, basic project creation | Done, verified |
| **Milestone 2**: DeepSeek, content schemas, batch generation, persistence of pieces | **Done, verified with a fake DeepSeek** (never called the real API yet) |
| UI redesign to the user's reference (warm glass, icon rail, Sora/Geist, pill controls) | Done, one screenshot review round |
| **Next: Milestone 3** Pexels/Unsplash providers, asset library, asset metadata, deduplication | Not started |
| M4 visual analysis, palette · M5 TTS, audio, FFmpeg renderers · M6 preview, regeneration, queue, export · M7 refinement · packaging | Not started |

Git: `main` on https://github.com/HasbiyallahuJafaru/aicontentstudio. Milestone 1 = b53f78b. **Milestone 2 + redesign are
not committed yet.** Commit/push only when the user asks.

## What exists

**Backend** (`apps/backend`, venv `.venv`, deps: pydantic, httpx)
- stdio JSON-lines RPC (`app/rpc.py`, method table `METHODS`); `app/events.py` writes responses/events to stdout.
  Events: `backend.ready`, `job.started|progress|completed|failed|cancelled` (payload = job row).
- Methods: `app.info`, `app.stats`, `settings.get|update`, `projects.create|list|get|delete`, `pieces.list`,
  `pieces.recent`, `jobs.start|cancel|latest`, `secrets.load` (Electron main only).
- DB migrations: `001_init` (projects, settings), `002_content` (content_pieces, generation_jobs).
- `app/creative/`: `schemas.py` (BatchPlan with distinct angles/subjects, PieceContent = quote/narration/visual/design
  hints/metadata; quote author must be null), `prompts.py` (provider-neutral messages), `model.py` (`CreativeModel`
  interface + `DeepSeekModel`, `get_model()` raises "Add your DeepSeek API key…" if none).
- `app/content.py`: pipeline = plan batch (avoiding recent quotes + narration openings) → write each piece; quote
  similarity via difflib ≥0.75 vs history+batch, up to 3 attempts then the piece is stored `failed` with the reason.
  Regenerating a project replaces its pieces. `recent()`, `stats()` for the dashboard.
- `app/jobs.py`: one thread per job, progress = real steps (plan, piece i of n), cancel between steps, `recover()` on
  startup marks interrupted jobs failed. Project status: draft → generating → ready | failed.
- Tests: `python -m unittest` = 16 tests (fake model; `httpx.MockTransport` for repair/retry/401/empty/wrong count).

**Desktop** (`apps/desktop`)
- Screens: Studio dashboard (hero with real stats + fanned frames showing the latest real quotes, recent projects),
  Create (glass brief form + live batch preview; "Create and generate" if a DeepSeek key is set, else "Save as draft"),
  Projects (list), Project page (Generate / Generate again with Ctrl+Enter, live stage + progress bar + Cancel,
  pieces with quote, narration, visual query, delivery, collapsible captions/metadata, failed-piece reasons, delete),
  Settings (glass sections: keys, AI, content defaults, storage).
- Design system (`src/styles/index.css` tokens + `glass` utility, `.ambient` glow, `.grain`; primitives in
  `src/components/ui.tsx`): warm charcoal, ember-orange accent, Sora display / Geist body, pill controls,
  14px fields, 26px panels. `useJob()` in `src/lib/studio.ts` listens to job events.
- `scripts/smoke.mjs` runs the real app against a local fake DeepSeek server: set keys, save a setting, create and
  generate 3 pieces, restart, check everything persisted. Screenshots → `%TEMP%/acs-smoke`.

**Verified 2026-09-19:** `npm test` from the root (16 unittest + tsc + build + smoke) passes; screenshots reviewed.
**Layout fix (2026-09-19):** the user's display is 1280×672 logical (1920×1080 at 150%). The window now sizes to the
screen work area (was a fixed 1440×900 that spilled off-screen), the shell grid uses `minmax(0,1fr)`, and the smoke
test asserts no sideways overflow on every screen at 1024×672, 1280×672, 1366×768 and 1920×1080.
**Not verified:** a real DeepSeek call (needs the user's key; prompt quality unknown), crash auto-restart,
`npm run dev` HMR, very long quotes/project names.

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # all checks
graphify update . # refresh the code map after changes
```

## Next: Milestone 3 (Pexels + Unsplash, asset library, dedup)
1. First, with the user's DeepSeek key: generate one real batch, read the output, tune `prompts.py` if quotes sound AI-ish.
2. Migration `003`: `assets` (PRD §17 fields incl. creator, source_url, license, phash, dominant colors placeholder
   until M4) + `asset_usage` (asset_id, piece_id, used_at).
3. `app/assets/`: `VisualProvider` interface, `PexelsProvider`, `UnsplashProvider` (httpx with the same ssl context,
   metadata + thumbnails first, download only the chosen asset; Unsplash download-tracking ping; human errors).
4. Candidate scoring (weights configurable in settings), exact hash + own dHash for near-duplicates, cooldown rules
   (PRD §18), select per piece using `visual.search_query` / `secondary_query`.
5. Library page (thumbnail grid, filters: type, provider, used/never used, 60 FPS) added to the rail.
6. Tests with fake providers; smoke with a fake provider server like the fake DeepSeek.

## Open decisions / notes
- Rail only shows built screens; Library, Queue, Exports arrive with their milestones.
- Platform-specific metadata adapters (PRD §69) come with export (M6); pieces currently hold one metadata set.
- Media folder is read-only in Settings; changing it needs a move step (later).
