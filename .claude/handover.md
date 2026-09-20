# Handover

Last updated: 2026-09-20 (Milestone 5 complete, not committed). Read this first in a new chat, then `.claude/CLAUDE.md` rules.
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
| **Milestone 5**: TTS, audio mixing, FFmpeg renderers, render UI | **Done and verified 2026-09-20: 63 backend tests green, full `npm test` (backend + tsc + build + smoke incl. real renders) green twice in a row. Nothing committed.** |
| M6 preview, regeneration, queue, export · M7 refinement, packaging | Not started |

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
  the project, asserts 3 rendered chips (+ after restart), asserts Library + swatches + filters, persistence.

**Verified 2026-09-20:** full `npm test` green twice in a row (63 backend tests incl. real-SAPI + real-ffmpeg,
tsc, build, smoke with 3 real 1080x1920 renders in ~9s). Screenshots reviewed: settings Narration/Render sections,
project page with rendered chips. WindowsTTS verified standalone. Windows package: not committed yet.
**Not verified:** real DeepSeek/Pexels/Unsplash calls (need user keys); analyser thresholds on real photos;
`npm run dev` HMR; developer link in a packaged build; splash loop seam; renders at non-1080 settings in the UI
(only tests); Kokoro end to end (model not downloaded).

## Resume here (after Milestone 5)

1. Commit/push M5 when the user asks (nothing committed yet; `git status` shows backend M5 files + UI + docs).
2. With the user's keys: one real DeepSeek batch + real Pexels downloads; sanity-check analyser thresholds
   (0.45 floor, 0.3 contrast scale) and tune `prompts.py` if quotes sound AI-ish. Watch a rendered video end to
   end and judge drawtext legibility/scrim strength on real footage. Pending since M3.
3. M6: preview, regeneration, queue, export (platform metadata adapters PRD §69, per-type asset pairs).

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # all checks
graphify update . # refresh the code map after changes
```

## Next after M5
- See "Resume here" above: commit M5 when asked, real-key verification, then M6.

## Open decisions / notes
- Rail shows Dashboard, Create, Projects, Library; Queue and Exports arrive with M6.
- Platform metadata adapters (PRD §69) come with export (M6); pieces hold one metadata set.
- Scoring weights are backend settings (`asset_weights`); user-facing knob is `asset_cooldown_days`.
- `video_image` renders both outputs per piece now (M5); per-platform pairs still land with export (M6).
- Palette text colour and brand clamps are hardcoded defaults (§24); per-user brand settings can come later.
- Kokoro is wired but optional; default TTS is Windows SAPI. `python -m app.tts download` fetches models.
