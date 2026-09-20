# Handover

Last updated: 2026-09-20 (Milestone 6 built, verified, not committed). Read this first in a new chat, then `.claude/CLAUDE.md` rules.
Update it after every phase.

## Where things stand

| PRD milestone | State |
|---|---|
| Phase 0 research | Done: `DECISIONS.md` |
| Milestone 1: Electron shell, React, Python process, SQLite, Settings, projects | Done, verified |
| Milestone 2: DeepSeek, content schemas, batch generation, jobs | Done, verified with a fake DeepSeek (never called the real API yet) |
| UI redesign (warm glass, icon rail, Sora/Geist) | Done, one screenshot review round |
| Milestone 3: Pexels/Unsplash pipeline (scoring, dedup, cooldown), Library | Done, verified with fake providers. Pushed: 9f03e6c + 126fa5c. |
| Milestone 4: visual analysis, HEX extraction, palette engine, composition detection | Done, verified on constructed images. Pushed: cb17653. |
| Splash + root README (user request) | Done. Pushed: b73d254 + 84a95ff. |
| Milestone 5: TTS, audio mixing, FFmpeg renderers, render UI | Done, verified, pushed: b815a50. |
| **Milestone 6**: preview, regeneration, queue, export | **Done, verified 2026-09-20: 74 backend tests green, full `npm test` (backend + tsc + build + smoke incl. preview/approve/regenerate/export) green. Nothing committed.** |
| M7 refinement, packaging | Not started |

Git: `main` on https://github.com/HasbiyallahuJafaru/aicontentstudio. Commit/push only when the user asks.

## What exists

**Backend** (`apps/backend`, venv `.venv`, deps: pydantic, httpx, Pillow)
- stdio JSON-lines RPC (`app/rpc.py`, `METHODS`); events: `backend.ready`, `job.started|progress|completed|failed|cancelled`.
- Methods: `app.info`, `app.stats`, `settings.get|update`, `projects.create|list|get|delete`, `pieces.list`,
  `pieces.recent`, `assets.list`, `renders.list`, `jobs.start(project_id, kind='generate'|'render')|cancel|latest`,
  `secrets.load` (Electron main only).
- Migrations: 001 projects/settings, 002 content_pieces/jobs, 003 assets/asset_usage, 004 analysis columns
  (subject_position, visual_complexity, temperature, quality_score), **005 `generation_jobs.kind` + `renders` table**
  (id, project_id, piece_id, kind video/image, local_path, duration).
- `app/creative/`: schemas, prompts, `CreativeModel` + `DeepSeekModel` (JSON mode, repair-once-retry-once;
  `ACS_DEEPSEEK_URL` env override).
- `app/content.py`: plan -> write pieces -> `assets.assign` (one visual per piece). Quote dedup difflib >=0.75,
  3 attempts. Progress counts 2n+1 steps. Piece status: written -> rendering -> ready (used by M5).
- `app/assets/`: `providers.py` (VisualProvider; Pexels photos+videos, Unsplash photos, download ping;
  `ACS_PEXELS_URL`/`ACS_UNSPLASH_URL` env overrides) + pipeline (metadata+thumbs first, suitability filter,
  PRD §78 quality gate 0.45, PRD §16 scoring with M4 analysis live, dHash dedup + cooldowns, winner downloaded;
  per-piece failures land in content `visual_error`).
- `app/visual.py` (M4): deterministic Pillow analysis on thumbnails (brightness/contrast/saturation/temperature/
  dominant HEX/subject_position/complexity), `quality()` floor 0.45, `palette()` -> PRD §23 tokens per piece
  (content `palette`), `themes_from_query()` feeds the category cooldown. NEAREST resize, deterministic, DB = cache.
- **M5:**
  - `app/tts.py`: `TTSProvider` (PRD §29) + `WindowsTTS` (SAPI via PowerShell; async subprocess, stdin text,
    uuid-named wav in media/audio, duration from `wave`) and `KokoroTTS` (kokoro-onnx, optional: human UserError
    until `pip install kokoro-onnx soundfile` + `python -m app.tts download`). `get_tts()` reads settings.
    WindowsTTS verified live.
  - `app/render.py`: PIL text composition (bundled Sora variable font `assets/fonts/`, OFL.txt included; greedy
    wrap; size ladder scaled to output width; `placement()` per PRD §26 with M4 subject_position; scrim gradient
    PNG from palette overlay). `FFmpegRenderer.render_video`: argv-array ffmpeg (§32), `-nostdin`, 9:16 crop,
    scrim overlay, per-line drawtext (fontfile quoted+escaped `'{C\:/...}'` - Windows colon needs BOTH), loudnorm
    narration (-16 LUFS, TP -1.5), optional music with volume + fades + amix normalize=0, source FPS preserved,
    still images -> 60fps slow push-in (zoompan), long sources -> middle segment (§65), short -> `-stream_loop -1`,
    `-progress pipe:1` parsed for per-piece progress, `-t narration+0.6`. stderr goes to a temp file (never a
    pipe) and a 180s no-progress watchdog kills wedged ffmpeg (see DECISIONS gotcha: the Electron stdin-inheritance
    hang). `validate_video` (§34): resolution, h264/aac, fps, duration. `render_image`: PIL 1080x1350 JPEG,
    subject-biased crop, scrim, text with shadow, `validate_image`.
  - `app/renders.py`: `render_project()` orchestration (§33): narration (asyncio.run around the TTS coroutine) ->
    render per piece per wanted kinds (format video_image -> both), piece status walking, per-piece `render_error`
    in content, renders rows, `renders.list_(project_id)`.
  - `app/jobs.py`: `start(project_id, kind)`; `_run` dispatches generate|render to content/renders; one active job
    per project regardless of kind. rpc: `renders.list`, jobs.start kind param.
  - `app/settings.py` additions: tts_provider ('windows' default | 'kokoro'), tts_voice, tts_speed, tts_volume,
    music_path, music_volume (<=0.5), render_crf (22), render_audio_bitrate ('192k'), render_width/render_height
    (1080x1920 default; §49 "output resolution" setting - tests set 540x960).
  - `tests/test_render.py`: composition units (wrap, size ladder, placement vs subject, escaping), real-SAPI TTS
    test (skipUnless win32), Kokoro-missing-model human error, real-ffmpeg integration at 540x960 (video validate,
    still->video 60fps, image 1080x1350), full render job (generation -> real video file swap -> FakeTTS ->
    kind='render' -> renders rows + piece ready). Test avoids other modules' fixture quote + wipes asset_usage so
    the full-suite run doesn't trip quote dedup or the visual cooldown.
- **M6:**
  - `app/platforms/` (PRD §69-73): youtube_shorts / instagram_reels+feed / tiktok adapters in one module — pure
    metadata shaping (title truncation, caption+hashtags limits, cover + file per platform, suggested_time
    heuristics), never publish. A platform whose required render is missing reports `unavailable` at export.
  - `app/export.py` (PRD §47, §68): export runs as jobs kind='export' (all or selected piece_ids) →
    `exports/<date>/NNN_<slug>/` with video_9x16.mp4, image_4x5.jpg, thumbnail.jpg (ffmpeg frame grab), caption.txt
    and metadata.json (base metadata + per-platform blocks); pieces walk to status 'exported'; `exports.list_`.
  - `app/content.py`: `regenerate(piece_id, scope)` (§43 quote/narration/design via one model call reusing the
    piece's plan item, quote dedup with 3 attempts; 'visual' re-runs assets.assign — cooldown pushes away from the
    current asset) and `approve(piece_id)` (ready→approved). Both drop stale renders → status 'written'.
  - `app/queue.py` (§46): pieces across projects with status + render counts, plus recent jobs; `queue.list`.
  - `app/jobs.py`: kind validate generate|render|export; export passes optional piece_ids; project status only
    flips to 'generating' for generate jobs. Migration 006: renders.fps/width/height + exports table.
  - `renders.py`: `_wanted_kinds` adds image when instagram_feed is targeted (§72 4:5 pair); one row per
    piece+kind (re-render replaces); fps/width/height recorded and returned by `renders.list_`.
  - Desktop: Preview modal (`components/Preview.tsx`) — native `<video controls>` + MP4/H.264/resolution/FPS/
    duration indicators, image fit/actual + before/after, Redo one part (Quote/Narration/Visual/Design), Approve,
    Export this piece; render chips open it. Rail gains Queue + Exports screens (stage tabs with counts;
    export runs with Open folder via guarded `app:openExportPath` IPC + Copy path). Project header gains Export.
  - `tests/test_m6.py`: adapters, regenerate (narration keeps everything else; visual picks a different asset;
    scope/failed guards), approve gating, export folder + metadata.json + statuses, queue.list.

**Desktop** (`apps/desktop`)
- Splash screen every launch: bundled 60fps waves clip `src/assets/splash.webm` (8s VP9 ~2MB, from "Waves off of
  dock at Boston harbor" by Adam S. Keck, CC BY-SA 4.0; credit bottom-right + README). "Let's create content"
  enters on Create; "Meet our developer" -> https://hasbiyallahu.xyz via `app:openExternal` (https-only IPC).
  prefers-reduced-motion pauses the video; shortcuts inert until entry; splash overflow checked on `#root > div`.
- Screens: Dashboard, Create, Projects, Project page (progress, pieces, `visual_error`, captions, delete),
  Settings (keys, AI, content defaults incl. cooldown, storage), Library (grid, swatches, Type/Provider/Usage/
  Quality filters, 60 FPS badge, usage counts).
- `media://` privileged protocol serves `<dataDir>/media` (host+pathname - Chromium collapses `media:///a/b` to
  `media://a/b`); CSP img-src includes `media:`. Design tokens per `src/styles/index.css`; `useJob()`, `mediaUrl()`.
- M5 UI: Settings "Narration" (engine windows/kokoro, voice, speed, volume) + "Render" (quality CRF, music path +
  volume) sections; Project page Render button (jobs.start kind='render', disabled while a job runs or no piece
  has an asset) with accent rendered chips (Video X.Xs / Image) from `renders.list` on each piece row.
  - `scripts/smoke.mjs`: fake DeepSeek + fake Pexels; enters through the splash both launches; generates 3 pieces
    with visuals, swaps the fake asset bytes for real 14s ffmpeg clips, sets narration speed in Settings, renders
    the project, previews a piece (video + indicators), approves + regenerates narration + re-renders, exports the
    project (Exported chips), checks Queue stage tabs and the Exports run, screenshots everything.

**Verified 2026-09-20:** full `npm test` green (74 backend tests, tsc, build, smoke with the full M6 flow incl.
export folders on disk). Screenshots reviewed: preview modal with indicators, project with exported chips, queue
tabs, exports run. WindowsTTS + real ffmpeg verified. Nothing committed yet (M6).
**Not verified:** real DeepSeek/Pexels/Unsplash calls (need user keys); analyser thresholds on real photos;
`npm run dev` HMR; developer link in a packaged build; renders at non-1080 settings in the UI; Kokoro end to end.

## Resume here (after Milestone 6)

1. Commit/push M6 when the user asks (nothing committed since b815a50 M5).
2. M7: refinement pass + packaging (electron-builder NSIS + PyInstaller-frozen backend in resources/backend,
   bundled ffmpeg per DECISIONS). Also the calendar view (§74) only if the user asks for it — it is not in the
   M6/M7 scope the handover tracks.
3. Real-key verification round (pending since M3): one real DeepSeek batch + real Pexels downloads; watch a
   rendered video end to end; tune prompts/thresholds if needed.

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # all checks
graphify update . # refresh the code map after changes
```

## Next after M6
- See "Resume here" above: commit M6 when asked, then M7 (refinement + packaging), plus the real-key
  verification round pending since M3.

## Open decisions / notes
- Rail shows Dashboard, Create, Projects, Library; Queue and Exports arrive with M6.
- Platform metadata adapters (PRD §69) come with export (M6); pieces hold one metadata set.
- Scoring weights are backend settings (`asset_weights`); user-facing knob is `asset_cooldown_days`.
- `video_image` renders both outputs per piece now (M5); per-platform pairs still land with export (M6).
- Palette text colour and brand clamps are hardcoded defaults (§24); per-user brand settings can come later.
- Kokoro is wired but optional; default TTS is Windows SAPI. `python -m app.tts download` fetches models.
