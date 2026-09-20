# Handover

Last updated: 2026-09-20 (Milestone 7 complete + user feedback rounds 1-3 + crash fixes — everything committed
and pushed to `main` through the "director-cut renders" commit. Full `npm test` green: 115 backend tests, tsc,
build, smoke synced to the wizard Create flow and video_image defaults. Next: real-key verification rounds,
then M8 packaging). Read this first in a new chat, then `.claude/CLAUDE.md` rules (product direction lives
there too). Update this file after every phase.

## Where things stand

| PRD milestone | State |
|---|---|
| Phase 0 research | Done: `DECISIONS.md` |
| Milestone 1: Electron shell, React, Python process, SQLite, Settings, projects | Done, verified |
| Milestone 2: DeepSeek, content schemas, batch generation, jobs | Done, verified with a fake DeepSeek (real API still unverified) |
| UI redesign (warm glass, icon rail, Sora/Geist) | Done, one screenshot review round |
| Milestone 3: Pexels/Unsplash pipeline (scoring, dedup, cooldown), Library | Done, verified with fake providers. Pushed: 9f03e6c + 126fa5c |
| Milestone 4: visual analysis, HEX extraction, palette engine, composition detection | Done. Pushed: cb17653 |
| Splash + root README | Done. Pushed: b73d254 + 84a95ff |
| Milestone 5: TTS, audio mixing, FFmpeg renderers, render UI | Done. Pushed: b815a50 |
| Milestone 6: preview, regeneration, queue, export | Done. Pushed: 8f78c3c |
| **Milestone 7 (redefined)**: branding + ClipperAi engine + Buffer/Metricool publishing + genres + director-cut renders | **Done, verified with fakes, pushed** (`fae7ea0` M7, then feedback rounds: `509edd6`/`ed08bf3`/`d694d4d`, `0803393` genres, `c658b74` director-cut, `b8701f0` blank topic, `b38fb3b` fullscreen). Real-key rounds pending. |
| M8: refinement, packaging | **Done 2026-09-20.** `npm run package` from the repo root: PyInstaller freezes the backend (the spec now bundles `app/migrations`, without which the frozen first run had no tables), `scripts/fetch-ffmpeg.mjs` puts ffmpeg+ffprobe in `resources/ffmpeg` (copies from PATH, or downloads release-essentials with `ACS_FFMPEG_DOWNLOAD=1`), electron-builder writes a per-user NSIS installer to `apps/desktop/release/` (~310 MB, 1.1 GB unpacked). `backend.ts` spawns `backend.exe` when present, venv python otherwise. ffmpeg is resolved through `config.FFMPEG`/`FFPROBE` from `ACS_FFMPEG`/`ACS_FFPROBE`. **Verified:** `npm run smoke:packaged` launches the built app, the frozen backend migrates and reports ready, app.info answers. electron-builder needs `NODE_OPTIONS=--use-system-ca` on this machine. |

Git: `main` on https://github.com/HasbiyallahuJafaru/aicontentstudio. Commit/push only when the user asks.

## What exists

**Backend** (`apps/backend`, venv `.venv`, deps: pydantic, httpx, Pillow, opencv-python, yt-dlp, tzdata,
kokoro-onnx + soundfile)
- stdio JSON-lines RPC (`app/rpc.py`, `METHODS`); events `backend.ready`, `job.started|progress|completed|failed|cancelled`.
- Methods: `app.info`, `app.stats`, `settings.get|update`, `projects.create|list|get|delete|set_voice`,
  `pieces.*`, `assets.list`, `renders.list`, `clips.list|review`, `exports.list`, `queue.list`,
  `jobs.start(project_id, kind='generate'|'render'|'export'|'clip', piece_ids)|cancel|latest`,
  `tts.voices`, `publish.*` (12: buffer connection/connect_url/disconnect/channels/publish/calendar/
  publications/remove, host status/save, metricool status/call), `secrets.load` (Electron main only).
- Migrations 001–008: projects/settings, content_pieces/jobs, assets/asset_usage, analysis columns,
  renders + kind, exports, **007 `clips`**, **008 `publications` + `credentials` (DPAPI-encrypted)**.
- `app/creative/`: schemas (model strings are **trimmed to caps**, not rejected — a 94-char angle must not kill
  a plan), prompts (`GENRES` — the six genre voice specs + attribution rules; hook-first, second-person,
  concrete-image writing system modelled on soulsigh/hopecore, MotivationHub, Daily Stoic; per-project
  `target_seconds` narration guidance), `CreativeModel` + `DeepSeekModel` (JSON mode, repair-once-retry-once,
  `ACS_DEEPSEEK_URL` override).
- `app/content.py`: plan → write pieces → `assets.assign`; quote dedup difflib ≥0.75, 3 attempts; `regenerate`
  (quote/narration/design/visual), `approve`; piece status written → rendering → ready → approved → exported.
- `app/assets/`: Pexels/Unsplash providers (`ACS_PEXELS_URL`/`ACS_UNSPLASH_URL` overrides) + pipeline
  (suitability, quality gate 0.45, scoring, dHash dedup + cooldowns, winner downloaded, `visual_error` per piece).
- `app/visual.py` (M4): deterministic Pillow analysis, `palette()` tokens per piece, subject_position.
- `app/tts.py`: **default engine Kokoro** — 82M int8 quantized (`kokoro-v1.0.int8.onnx` from the kokoro-onnx
  GitHub releases; `python -m app.tts download`; verified live; handles the 0.6 sync `create()` API) +
  WindowsTTS (SAPI) fallback. `get_tts(provider)` accepts an override; `voices()` lists Kokoro (54) + Windows
  names for the Create picker.
- `app/render.py`: **`render_video(shots=...)` is a director-cut editor** — per-shot seek/motion
  (zoom-in / pan-lr / zoom-out / push-in), still cutaways merged between video shots, concat, genre color grade
  (LOOKS; `auto` resolves per genre), vignette + film-grain dressing, optional karaoke ASS subtitles, optional
  scrim/quote legacy overlay (unused since the user removed quote text from videos), loudnorm narration +
  optional music with fades. 30/60 fps via `out_fps`. `render_image` unchanged (1080×1350, quote still drawn).
  ffmpeg discipline: argv arrays, `-nostdin`/DEVNULL stdin, stderr → temp file, 180s stall watchdog.
- `app/renders.py`: `render_project(project_id, report, piece_ids)` — builds the shot plan (`_shots_for`:
  2-3 motion cuts + a still cutaway from the asset's cover frame; short sources loop), genre look resolution
  (GENRE_LOOKS), subtitle ASS synthesis (`_subtitles_ass` — proportional word timings, not forced-aligned),
  per-piece status walking, renders rows.
- `app/clipper/` (Phase B, ported from the user's ClipperAi repo): `ff.py` (ffmpeg discipline), `acquire.py`
  (yt-dlp), `transcribe.py` (Groq Whisper via httpx multipart, chunk+overlap stitching, `ACS_GROQ_URL` override),
  `select.py` (two-pass DeepSeek, strict parsing, `snap`), `crop.py` (YuNet face tracking, bundled model),
  `captions.py` (karaoke ASS, bundled Montserrat), `render_clip.py` (clip render + cover, 30/60 fps).
- `app/clips.py`: clip orchestration — acquire → title→project name → transcript cache
  (`media/clipwork/<key>/transcript.json`) → find_clips → snap + render into `media/clips/<pid>/`, rows in DB.
- `app/publish/` (Phase C): `oauth.py` (Buffer PKCE public client, loopback `127.0.0.1:8787/callback`,
  single-use refresh rotation), `host.py` (hand-rolled SigV4 PUT to the user's S3-compatible bucket — Buffer has
  NO upload API), `buffer.py` (GraphQL channels/publish/calendar/publications/remove; no local queue — Buffer
  schedules server-side), `metricool.py` (minimal stdlib MCP client for `ai.metricool.com/mcp`, `X-Mc-Auth`),
  `store.py` (DPAPI-encrypted credentials table).
- `app/export.py`: piece exports (`exports/<date>/NNN_<slug>/` + caption.txt + metadata.json) and clip exports
  (clip.mp4, cover.jpg, captions.ass, caption.txt, metadata.json with per-platform posts).
- `app/cli.py`: `python -m app.cli projects|clips|export|channels|publish --at|metricool`.
- `app/jobs.py`: kinds generate|render|export|clip; render accepts piece_ids (per-piece re-render);
  cancel/recover account for clip projects.
- Tests (113): test_content (incl. over-long model line trimming), test_assets, test_visual, test_backend,
  test_render (incl. the whole multi-shot filter graph + still/motion variants), test_m6, test_clipper_port
  (21), test_publish (13 — fake Buffer/auth/host/MCP servers; real loopback OAuth; independent SigV4 check).

**Desktop** (`apps/desktop`, Electron + React + Tailwind 4)
- Splash (bundled waves clip + 3 developer links) → Shell (icon rail with hover spin + label pill, Created-by
  footer) → Dashboard / Create / Projects / Project / Library / Queue / Exports / Settings.
- Create: **mode toggle** (Write content | Clip from video). Write form: topic autocomplete, **Genre** dropdown
  (was tones), output, quantity, platforms, **Narration voice** picker (`tts.voices`), **Video length**
  (Auto/~15/~30/~45/~60s), **Subtitles** toggle, **Frame rate** 30/60, **Look** (Auto genre grade + presets),
  Blur background, Parallax. Clip form: source, orientation, count, captions, length, fps.
- Project page: progress bar, piece rows with render chips, Preview modal (video/image, indicators, Redo
  quote/narration/visual/design, **Narration voice swap** → set_voice + per-piece re-render, Approve, Export),
  Export/Render/Generate-again; clip projects branch to `components/Clips.tsx` (review rows, approve/reject,
  clip preview with per-platform post copy, Publish dialog, Export, Clip again). Auto-scroll to finished
  content on job completion. Create Ctrl+Enter is a window-level listener (form-level one missed keystrokes
  after using a dropdown).
- Settings: API keys (DeepSeek/Pexels/Unsplash/Groq/Metricool, DPAPI-backed safeStorage), AI, content defaults
  (incl. **default genre**), Narration (engine/voice/speed/volume), Render (CRF, music), **Publishing**
  (Buffer client id + connect flow with polling, media host for Buffer video hosting, Metricool check), Storage.
- `electron/secrets.ts`: safeStorage allowlist (DEEPSEEK, PEXELS, UNSPLASH, GROQ, METRICOOL).
  `electron/backend.ts`: spawns `.venv` python (dev); **call() guards closed stdin** (fixes
  ERR_STREAM_WRITE_AFTER_END crash when writing after the backend stopped).
- `scripts/smoke.mjs`: fake DeepSeek (content + clip passes) + fake Pexels + fake Groq; two launches; full
  social flow (generate → render → preview → approve → regenerate → export → queue/exports/library) and a full
  clip flow (12s fixture → Clip create → review → approve → export). Renderer console errors captured.
- M8 (in flight): `apps/backend/backend.spec` (PyInstaller, `dist/backend/backend.exe`), electron-builder
  installed (no config yet), ffmpeg bundling + backend.ts packaged branch still to do.

**Verified 2026-09-20:** `npm test` green through feedback round 3 (113 backend tests, tsc, build, smoke).
Kokoro int8 verified live (real wav generated). Multi-shot/blur/parallax/subtitle render verified by frame
extraction. Real-loopback Buffer OAuth verified in tests.
**Not verified (needs the user's keys / real network):** real DeepSeek output quality per genre (no key on this
machine — repo has no `.env`); real Pexels/Unsplash; real YouTube clip through yt-dlp + Groq; Buffer connect +
publish against the real API; Metricool `schedule_post` schema + UI mapping; `npm run dev` HMR; packaged build;
Kokoro narration quality by ear (engine verified live, samples not judged).

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # backend unittest (113) + typecheck + build + smoke
graphify update . # refresh the code map after changes
```

## User feedback rounds 4-5 + fixes (2026-09-20, implemented)
- **Crash fix 1**: a DeepSeek reply with an over-long angle/visual_subject (94 chars vs the 80 cap) failed the
  whole plan. Model-authored strings are now **trimmed to their caps** in schemas.py, not rejected.
- **Crash fix 2**: `backend.call()` wrote into a backend stdin that had already ended ->
  ERR_STREAM_WRITE_AFTER_END dialog. call() now guards closed streams and answers with an error reply.
- **Blank default topic** is the shipped default (user's migrations 009/010: blank topic, quantity 1, kokoro
  am_adam voice, hopecore genre; legacy values map forward). A guard that still rejected blank topics was removed.
- **Maximize = fullscreen**: `win.on('maximize')` -> setFullScreen; F11 toggles; Esc exits. Verified with a
  playwright check (maximize() flips isFullScreen, window covers the display).
- **UnidentifiedImageError fix**: a video asset targeted at instagram_feed (image render) handed the .mp4 to
  PIL. renders.py now **frame-grabs video assets** (`render.thumbnail` at mid-duration, retry-from-0 if the seek
  is past EOF) and renders the 4:5 from that frame; render_image raises a human UserError for non-images.
- **Create page is a 3-step wizard** (user redesign): Brief -> Delivery -> Look; Ctrl+Enter walks forward and
  submits on the last step (window-level listener). Defaults: blank topic, video_image format, hopecore genre.
- **Smoke synced**: walks the wizard (topic fill, genre select, Ctrl+Enter with per-step waits), expects
  video_image renders (6 chips, 4 after narration redo), restart assertions updated.

## Feature backlog / product direction (user-supplied 2026-09-20)

**Edit quality: implemented 2026-09-20.** `app/edit.py` holds the grammar (per-genre cadence, transition, motion,
grade, dressing, music duck). A piece now downloads a pool of up to 4 distinct visuals (`assets.SHOTS`, in-piece
perceptual dedupe) instead of one clip; `renders._shots_for` cuts on real narration word timings (Groq STT when a
key is set, estimator otherwise); `render.render_video` joins every shot with `xfade`, supersamples stills before
`zoompan`, ramps the turn shot, applies the genre grade + halation + grain + bars, ducks music with
`sidechaincompress`, and fails a render that opens on black. Tests: `tests/test_edit.py` plus the heavy-graph and
black-frame cases in `tests/test_render.py`. Deviations and what is still open are at the top of section 5 of
`.claude/edit-grammar.md`.

**Spec: `.claude/edit-grammar.md`** (written 2026-09-20) is the director's spec for how a piece is cut:
audit of why renders read as a slideshow, per-genre cadence/grade/transition grammar, the locally verified
ffmpeg capability table, and a six-phase refactor (A shot pool per piece, B cut to the voice, C real LUT grades,
D transitions and ramps, E ducked audio, F validation). Phase A is the unlock; nothing else matters without it.

North star: **turn raw long-form content into polished, platform-ready short-form content with as little manual
editing as possible** — every feature should improve content quality, automation, publishing, platform
compatibility, user control, speed, reliability, cost efficiency, or professional appearance.

1. **IP detection / YouTube-compatible network routing** (backlog / research): detect the app's public IP,
   explore network configurations compatible with YouTube access; proxy/VPN support only if legitimate; never
   hard-code IP ranges; stay inside YouTube's ToS.
2. **Metricool** (base done): inspect the real `schedule_post` MCP tool schema with a real key and build a
   proper "post via Metricool" UI mapping (today: raw passthrough via `publish.metricool_call` + CLI).
3. **Buffer** (base done): real-key verification end to end (OAuth app registration with redirect
   `http://127.0.0.1:8787/callback`, R2 bucket, publish now + scheduled, confirm Buffer fetches from the bucket).
   Principle that holds: the app must NOT become the user's social-media credential store — OAuth only,
   DPAPI-encrypted tokens, retain the minimum.
4. **Premium short-form quality** (continuous): smart selection, strong hooks, dead-space removal, natural
   pacing, word-level captions in platform safe areas, subject-tracked reframing, clean audio (noise reduction,
   balancing, music ducking), sparing transitions, professional typography. Priority: story > hook > pacing >
   clarity > visual > audio > platform-safe composition > brand consistency. Never "looks AI generated."

## Resume here (new chat — real-key verification, then M8)

1. `git log --oneline -1` + read this file + DECISIONS.md + CLAUDE.md, then `npm test` once to confirm green.
2. Real-key verification (keys live in Settings or repo `.env`; none present as of 2026-09-20):
   - DeepSeek: generate one batch per genre and tune the genre voice specs against the output.
   - Clips: real YouTube link end to end (yt-dlp bot-check, Groq transcription, transcript cache hit, face-crop
     + caption quality).
   - Buffer: register the OAuth app (public/PKCE) at developers.buffer.com with redirect
     `http://127.0.0.1:8787/callback`, connect in Settings, add an R2 bucket, publish now + scheduled; confirm
     Buffer fetches the video from the bucket.
   - Metricool: paste the API key, `python -m app.cli metricool tools`, then wire the `schedule_post` UI mapping.
3. Finish M8: verify the frozen exe (RPC + a real render), electron-builder NSIS config, bundle
   `resources/backend` + ffmpeg, backend.ts packaged branch (spawn `backend.exe`, prepend bundled ffmpeg to
   PATH), build and launch the installer.
4. Refinement polish: beat-detect cuts / content-aware shot selection, forced-alignment subtitles.

## Open decisions / notes
- Genres replaced tones everywhere; stored settings/briefs with old tone names map forward
  (`_LEGACY_TONES` in settings.py, e.g. cinematic → cinema). Existing installs may still have
  `tts_provider: 'windows'` stored — the kokoro default applies to fresh rows; per-project voice picks sidestep it.
- ClipperAi's two-model selection (flash scan / pro picks) collapsed into the single `ai_model` setting —
  revisit if pass-2 copy quality disappoints with a cheap model.
- Subtitle timing on social videos is proportional to the narration audio, not forced-aligned — real word
  timestamps would need an alignment pass (clips already have Whisper timings).
- Whether clip export should also drive publishing directly from the clip's per-platform posts (Phase C UI).
- Smoke flakiness: don't run heavy ffmpeg work in parallel with the smoke; run it standalone.
- M8 decisions pending: bundle the Kokoro model in the installer vs. keep download-on-demand; app icon.
