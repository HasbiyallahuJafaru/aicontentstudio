# Handover

Last updated: 2026-09-19. Read this first in a new chat, then `.claude/CLAUDE.md` rules. Update it after every phase.

## Where things stand

| PRD milestone | State |
|---|---|
| Phase 0 research | Done: `DECISIONS.md` |
| Milestone 1: Electron shell, React, Python process, SQLite, Settings, basic project creation | Done, verified |
| Milestone 2: DeepSeek, content schemas, batch generation, persistence of pieces | Done, verified with a fake DeepSeek (never called the real API yet) |
| UI redesign to the user's reference (warm glass, icon rail, Sora/Geist, pill controls) | Done, one screenshot review round |
| Milestone 3: Pexels/Unsplash providers, asset pipeline (scoring, dedup, cooldown), Library page | Done, verified with fake providers (never called the real APIs yet). Pushed: 9f03e6c + 126fa5c. |
| **Milestone 4**: visual analysis, HEX extraction, palette engine, composition detection | **Done, verified with constructed test images** (no real photos yet) |
| M5 TTS, audio, FFmpeg renderers · M6 preview, regeneration, queue, export · M7 refinement · packaging | Not started |

Git: `main` on https://github.com/HasbiyallahuJafaru/aicontentstudio. Commit/push only when the user asks.

## What exists

**Backend** (`apps/backend`, venv `.venv`, deps: pydantic, httpx, Pillow)
- stdio JSON-lines RPC (`app/rpc.py`, `METHODS`); events: `backend.ready`, `job.started|progress|completed|failed|cancelled`.
- Methods: `app.info`, `app.stats`, `settings.get|update`, `projects.create|list|get|delete`, `pieces.list`,
  `pieces.recent`, `assets.list`, `jobs.start|cancel|latest`, `secrets.load` (Electron main only).
- Migrations: 001 projects/settings, 002 content_pieces/jobs, 003 assets/asset_usage, 004 analysis columns
  (subject_position, visual_complexity, temperature, quality_score). dominant_colors/brightness/saturation/contrast
  were in 003; themes feed the category cooldown (filled from the selecting search query's content words).
- `app/creative/`: schemas, prompts, `CreativeModel` + `DeepSeekModel` (JSON mode, repair-once-retry-once, retries;
  `ACS_DEEPSEEK_URL` env override).
- `app/content.py`: plan → write each piece → `assets.assign` (one visual per piece). Quote dedup via difflib ≥0.75,
  3 attempts then piece `failed`. Progress = 2n+1 real steps. Completed stage "Done".
- `app/assets/`: `providers.py` (`VisualProvider`, Pexels photos+videos picking portrait mp4 closest to 1080×1920,
  Unsplash photos only, download-tracking ping via `links.download_location`; `ACS_PEXELS_URL`/`ACS_UNSPLASH_URL`
  env overrides) + `__init__.py` pipeline: metadata + thumbnails first, suitability filter (portrait, ≥720px,
  4–90s), quality gate (PRD §78: `quality < 0.45` never offered), scoring with PRD §16 weights — relevance (rank),
  novelty (usage), visual_quality (resolution + technical quality), composition (subject off-center = keeps the
  middle free for text), brand (`no_neon` saturation clamp), color richness; motion scores 0 until M5. Dedup:
  `(provider, provider_asset_id)` UNIQUE + dHash (hamming ≤10 = similar → cooldown; same asset reused only when a
  query's pool is exhausted, then least-used). Winner downloaded to `media/assets/`, thumbnail to `media/thumbs/`
  (extension sniffed from bytes). Pre-M4 library rows get their analysis backfilled on next reuse. Per-piece
  failures stored as `visual_error` in the piece content; no keys → phase skipped with an honest stage message.
- `app/visual.py` (M4): deterministic Pillow-only analysis on thumbnails at download time — brightness, contrast
  (pstdev/0.3), saturation, temperature (warm/neutral/cool), up to 3 dominant HEX colors (quantize + near-dup
  merge), subject_position via gradient energy in thirds (center on ties), visual_complexity. `quality()` =
  exposure + real contrast + no-neon + colour richness (floor 0.45). `palette(dominant)` → PRD §23 design tokens
  {primary, secondary, dark, light, text, overlay} clamped to brand identity (sat ≤0.5, lightness windows,
  contrast-checked text colour) — stored on each piece as `content["palette"]` for the M5/M6 renderers.
  Analysis resizes with NEAREST (no blend colours) and is deterministic; the DB row is the analysis cache (§63).
- `app/jobs.py`: one thread per job, cancel between steps, recover() on startup. draft → generating → ready|failed.
- Tests: `python -m unittest` = 53 tests (fake model/providers, httpx.MockTransport for provider parsing/auth/
  download-ping, analysis on constructed BMPs: solid/stripes/inverted/temperature/subject-position, palette clamps
  and text contrast, quality floor, cooldowns, fallback, job integration).

**Desktop** (`apps/desktop`)
- Splash screen (first thing every launch): full-bleed 60fps open-water clip (`src/assets/splash.webm`, 8s VP9
  ~2MB, bundled locally so it works offline; re-encoded from "Waves off of dock at Boston harbor" by Adam S. Keck,
  CC BY-SA 4.0 via Wikimedia Commons - credit shown bottom-right and in the README). Intro copy + two pill buttons:
  "Let's create content" enters the app on the Create page; "Meet our developer" opens https://hasbiyallahu.xyz via
  a new `app:openExternal` IPC handler (https-only; the app otherwise blocks all navigation and window opens).
  `prefers-reduced-motion` pauses the video; on video error a dark scrim remains. Shortcuts (Ctrl+N/Ctrl+,) are
  inert until the user enters. The splash has no `<main>`, so the smoke checks overflow on `#root > div`.
- Screens: Dashboard, Create, Projects, Project page (live job progress, pieces with quote/narration/visual/
  delivery, `visual_error` shown under Visual, captions metadata, delete), Settings (keys, AI, content defaults
  incl. Asset cooldown, storage), Library (thumbnail grid, swatches from dominant colors, filters: Type, Provider,
  Usage All/Never used/Recently used, Quality All/High ≥0.6, duration + 60 FPS badge, usage count + last used).
- `media://` privileged protocol serves `<dataDir>/media` to the sandboxed renderer with traversal guard; handler
  resolves host+pathname (Chromium collapses `media:///a/b` to `media://a/b`). CSP img-src includes `media:`.
- Design system per `src/styles/index.css`; primitives in `src/components/ui.tsx`; `useJob()`, `mediaUrl()` in
  `src/lib/studio.ts`.
- `scripts/smoke.mjs`: fake DeepSeek + fake Pexels (striped BMP thumbs so dHashes differ); generates 3 pieces with
  visuals, asserts Library cards + swatches + filters, restarts and checks persistence. Screenshots → `%TEMP%/acs-smoke`.

**Verified 2026-09-19:** `npm test` from the root (53 unittest + tsc + build + smoke) passes; screenshots reviewed
(splash with video + both buttons, Create page entry, Library with swatches + Quality filter, Project page,
Settings). Smoke enters through the splash on both launches. Root README.md written (status, architecture, setup,
attribution).
**Not verified:** real DeepSeek / real Pexels / real Unsplash calls (need the user's keys), Unsplash end to end
(only Pexels faked in smoke), real photos vs constructed test images for the analyser thresholds (0.45 floor,
0.3 contrast scale are first guesses — revisit with real downloads), video motion (M5, needs FFmpeg frames),
`npm run dev` HMR, very long strings, the developer link in a packaged build (opens the OS browser via
shell.openExternal; untested manually), splash loop seam after 8s.

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # all checks
graphify update . # refresh the code map after changes
```

## Next: Milestone 5 (TTS, audio, FFmpeg renderers)
1. First, with the user's keys: one real DeepSeek batch + real Pexels downloads; sanity-check the analyser
   thresholds on real assets (quality floor 0.45, contrast scale 0.3) and tune `prompts.py` if quotes sound AI-ish.
   (Pending on the user since M3 — everything else is verified against fakes.)
2. M5 per PRD §29-31, §108: `TTSProvider` interface (Kokoro-onnx first, see DECISIONS), narration audio per piece,
   FFmpeg subprocess renderers for video (9:16 1080×1920, source FPS preserved honestly per §19) and image output,
   text placement using `subject_position` + palette tokens from M4, audio mixing with music (user-supplied only).
3. FFmpeg is on PATH (9.0.1) on this machine; renderers run as subprocesses with argument arrays (PRD §32/§33).

## Open decisions / notes
- Rail shows Dashboard, Create, Projects, Library; Queue and Exports arrive with M6.
- Platform metadata adapters (PRD §69) come with export (M6); pieces hold one metadata set.
- Scoring weights are backend-configurable (settings `asset_weights`); the user-facing knob is `asset_cooldown_days`.
  No Settings UI for weights — add if the user wants to tune.
- `video_image` brief format picks one visual per piece (plan's type); per-type pairs arrive with export (M6).
- Media folder is read-only in Settings; changing it needs a move step (later).
- Palette text colour and brand clamps are hardcoded defaults (§24 identity); per-user brand settings can come later.
