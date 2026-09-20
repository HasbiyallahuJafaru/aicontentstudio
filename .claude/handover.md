# Handover

Last updated: 2026-09-20 (Milestone 7 Phase C — Buffer + Metricool publishing + CLI — implemented, backend 108
tests green; full npm test verify in progress; nothing committed). Read this first in a new chat, then
`.claude/CLAUDE.md` rules. Update it after every phase.

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
| **Milestone 6**: preview, regeneration, queue, export | **Done, verified, pushed: 8f78c3c.** |
| **Milestone 7 (redefined)**: developer branding + ClipperAi engine merge + Buffer/Metricool publishing | **Phase A + B + C implemented (B verified with fakes; C backend-verified with fakes; real-key rounds pending). Nothing committed.** |
| M8 (was M7): refinement, packaging | Not started |

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
tabs, exports run. WindowsTTS + real ffmpeg verified. M6 pushed as 8f78c3c.
**Not verified:** real DeepSeek/Pexels/Unsplash calls (need user keys); analyser thresholds on real photos;
`npm run dev` HMR; developer link in a packaged build; renders at non-1080 settings in the UI; Kokoro end to end.

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # all checks
graphify update . # refresh the code map after changes
```

## Next after M6 — Milestone 7 was REDEFINED by the user (2026-09-20)

The user asked to pull in the feature set of their other project **ClipperAi** (`C:\Users\USER\Documents\ClipperAi`,
read its README.md — "YT-Clipper": long-video → shorts engine) instead of going to packaging next. New plan,
built in a **fresh chat** starting from this file:

**Phase A — developer branding (DONE, committed 2026-09-20):**
- `components/Branding.tsx`: SocialLinks (three inline interactive SVG logos — globe/website,
  LinkedIn, GitHub — hover states, opened via `studio.openExternal`, https-guarded) + CreatedBy footer.
- Splash: the three logos sit LOWER-LEFT (replaces the old "Meet our developer" text button); the Shell
  renders the "Created by Hasbiyallahu Jafaru" footer at the bottom of every page (flex column, pinned
  on short pages, follows content on long ones). Instagram was dropped by the user — only
  website/LinkedIn/GitHub. Hover shows a styled dark pill tooltip (custom, not the native `title`).
  Smoke updated (asserts 3 splash links).
- Rail buttons (Shell.tsx RailItem): on hover the icon does a full 360° spin (700ms ease-out-expo,
  reverses on leave) and the page name slides out from the icon's center to its right in a dark pill
  (200ms, reverses on leave); native `title` removed so only the custom label shows.

**Phase B — ClipperAi engine merge (the big one).** Port the engine in ClipperAi's `apps/backend/clipper.py`
(478 lines; do read that file + its `test_clipper.py` first) into `apps/backend/app/clipper/` as desktop modules,
keeping OUR job system (SQLite + threads, jobs.py), OUR storage (local `media/` served by `media://` — NOT R2),
and NO billing/accounts/Clerk/Paystack (user decision: the app is free and fully local). Port map (line refs into
ClipperAi's clipper.py):

| ClipperAi source | → new module | Notes |
|---|---|---|
| `acquire` (:160) + `downloader.py` | `app/clipper/acquire.py` | yt-dlp for links; local file path picks skip it. Progress per percent. |
| `transcribe` (:221) | `app/clipper/transcribe.py` | Groq Whisper, word-level JSON. New secret `GROQ_API_KEY` + Settings entry. |
| `ask_json` (:247), `parse_moments` (:261), `parse_picks` (:274), `find_clips` (:293), `snap` (:325) | `app/clipper/select.py` | Two-pass DeepSeek: moments → picks with score/hook/title/description/reason/hashtags + per-platform posts. Reuse the httpx + cert-store pattern from `app/creative/deepseek.py`. |
| `face_xs` (:325), `shots` (:354), `crop_filter` (:367) | `app/clipper/crop.py` | OpenCV largest-face tracking → dynamic 9:16 crop filter with shot-change deadzone. New dep `opencv-python`. |
| `ass_escape` (:387), `captions` (:391) | `app/clipper/captions.py` | Word-level karaoke ASS burned by ffmpeg subtitles filter (needs libass in the ffmpeg build — verify). |
| `render` (:419) | `app/clipper/render_clip.py` | Clip render + thumbnail 1s in. Copy our render.py subprocess discipline: argv arrays, `-nostdin`, stderr → temp file, stall watchdog. |

Wiring: new job kind `'clip'` in jobs.py (same dispatch pattern as generate|render|export), RPC methods
(`clips.*`), migration **007** (clips table: project, idx, start/end seconds, score, hook, review status, paths),
UI: "Clip from video" on Create (link or file), clip review list reusing the Preview modal patterns, approve →
export reuse. Tests: `tests/test_clipper_port.py`, porting the assertion patterns from ClipperAi's
`test_clipper.py` but with testsrc2 fixtures (no network downloads) like our test_render does.

**Phase B — ClipperAi engine merge (implemented 2026-09-20, uncommitted):**
- **Engine** `apps/backend/app/clipper/` (ported from ClipperAi's `clipper.py`, 1 file → 7 modules):
  - `ff.py`: the ffmpeg/ffprobe discipline every clip subprocess goes through — argv arrays, `-nostdin` +
    `stdin=DEVNULL` (the Electron stdin-inheritance hang), stderr → temp file (the stderr-PIPE exit-1 bug),
    hard timeout. `duration_of()` via ffprobe.
  - `acquire.py`: local file passes through (work dir = sha256[:16] of the file = transcript cache key); links
    download with yt-dlp (H.264/AAC sort, retries, per-percent progress, `YTDLP_PROXY` env escape hatch); bot-check
    DownloadError → human UserError.
  - `transcribe.py`: Groq Whisper `whisper-large-v3-turbo` via **httpx multipart** (NO openai SDK — same cert-store
    pattern as DeepSeek), 600s FLAC chunks +10s overlap, `stitch()` de-dupes the seam, bounded retries on
    429/5xx. `ACS_GROQ_URL` env override (smoke fake). New secret `GROQ_API_KEY` (Electron allowlist + Settings).
  - `select.py`: PASS1 (moments) / PASS2 (picks + copy) prompts, LIMITS, `fits()` word-boundary trim, Posts/Pick/
    Moment/Clip pydantic models, `parse_moments`/`parse_picks` (never trust model output), `snap()` to sentence
    boundaries. Both passes use the user's configured `ai_model` via `DeepSeekModel._chat` (ClipperAi used two
    hardcoded models; we kept ONE settings knob), max_tokens 64000, 3 parse attempts.
  - `crop.py`: YuNet face tracking (`assets/models/face_detection_yunet_2026may.onnx`, MIT) at 4 fps, `shots()`
    deadzone segmentation, `crop_filter()` dynamic 9:16/16:9/1:1 crop, centered fallback when no face.
  - `captions.py`: karaoke ASS (Montserrat ExtraBold in `assets/fonts/`, OFL.txt included), word highlight,
    orientation-aware PlayRes.
  - `render_clip.py`: clip render + cover frame at 1s, on `ff.ffmpeg`; ORIENTATIONS 9:16/16:9/1:1.
- **Wiring**: migration **007** `clips` table (project, idx, start_at/end_at, score, hook, title, description,
  hashtags/posts json, status ready|approved|rejected|exported, video_path/cover_path). Clip projects are normal
  project rows whose brief validates as `ClipBrief` (kind 'clip', source URL-or-path, n, min/max_len, orientation,
  burn_captions) — no separate entity. `app/clips.py` orchestrates: acquire → title→project name → transcript cache
  (`media/clipwork/<key>/transcript.json`) → find_clips → snap+render each clip into `media/clips/<pid>/`, rows in
  DB. Job kind `'clip'` in jobs.py (project status flips generating→ready; cancel/recover account for clips);
  RPC `clips.list|clips.review`; export branches for clip projects (per-clip folder: clip.mp4, cover.jpg,
  captions.ass, caption.txt, metadata.json incl. per-platform posts).
- **UI**: Create gains a "Write content / Clip from video" mode toggle (Choices); clip form = source input,
  orientation Select, Auto/3/5/10 count, Burned/Clean captions, Advanced min/max length; right panel is a pipeline
  explainer. Project page branches clip projects to `components/Clips.tsx` ClipWorkspace: job progress bar,
  Groq+DeepSeek key notes, clip rows (cover, title, score pill, duration, approve/reject/restore), preview modal
  (native video, hook/description/reason, per-platform post copy), Export + "Clip again". ProjectList rows show
  clip-specific state lines. Settings gains the Groq key field.
- **Tests**: `tests/test_clipper_port.py` (21) — ported ClipperAi's assertion patterns: snap, parse_moments/picks,
  stitch, standalone-chunk regression (fake `_post` measuring chunk durations), post caps, exact ASS lines,
  shot segmentation, real-ffmpeg burn/no-burn pixel diff + all three orientations, and a full clip job through
  jobs.start with fakes at the Groq/DeepSeek seams + export folder assertions + per-minute-count cap. Smoke gains
  a fake Groq server (`ACS_GROQ_URL`), clip branches in the fake DeepSeek, and a full UI clip flow (local 12s
  fixture → review → approve → export) with screenshots.

**Phase C — publishing integrations (implemented 2026-09-20, uncommitted):**
Research first (2026-09-20): **Buffer's API has no upload endpoint** (developers.buffer.com hosting-media guide:
"the Buffer API doesn't accept a file upload") — every published video must already sit at a stable public https
URL, so publishing requires the user's own S3-compatible bucket (Cloudflare R2 works). **Metricool's MCP** is
`https://ai.metricool.com/mcp`; header auth `X-Mc-Auth: <API key>` (Account Settings > API) works — n8n uses it —
so no OAuth dance needed there. Package: `apps/backend/app/publish/`:
- `store.py`: credentials the Python side owns (Buffer OAuth tokens, host keys, pending OAuth states) in the
  `credentials` table (migration **008**, which also adds `publications`), encrypted with Windows **DPAPI via
  ctypes** (the primitive safeStorage wraps; ponytail: plaintext off-Windows dev only).
- `oauth.py`: Buffer OAuth 2 Authorization Code + PKCE with a **public client** (no secret; the user registers
  their own OAuth app at developers.buffer.com, adds `http://127.0.0.1:8787/callback` as redirect, pastes the
  client id in Settings). A loopback `HTTPServer` on 8787 catches the browser reply, exchanges the code, stores
  tokens; single-use refresh tokens rotate atomically on refresh; failed refresh removes the connection.
- `host.py`: SigV4 PUT (~40 lines, hand-rolled — no boto3) of each published clip to the user's bucket under an
  unguessable name; returns the public URL. Settings: endpoint/bucket/public URL/region (settings row) + keys
  (credentials store).
- `buffer.py`: GraphQL port of ClipperAi's publishing (createPost/post/deletePost, channels with `usable`
  filter, post_input per-network copy incl. YouTube title/category and reel thumbnails) cut down for one local
  user: **no workspace keys, no local queue/worker** (Buffer holds scheduled posts itself), 30-day horizon,
  per-(project, clip, channel) duplicate guard, `publications` status refresh on read (once a minute), unschedule
  (sent posts refuse: delete on the network).
- `metricool.py`: minimal stdlib **MCP client** (streamable HTTP: initialize -> notifications/initialized ->
  tools/list -> tools/call; JSON or SSE replies; Mcp-Session-Id + MCP-Protocol-Version handled) with X-Mc-Auth.
  `status()` = tools/list as the connection check.
- RPC: 12 `publish.*` methods (buffer connection/channels/publish/calendar/publications/remove, host
  status/save, metricool status/call). Settings gain `buffer_client_id` + host fields; secrets gain
  **METRICOOL_API_KEY**. UI: Settings "Publishing" section (Buffer connect flow with polling, host config,
  Metricool check) and a Publish dialog on approved clips (channel picker, post now / datetime-local schedule).
- `app/cli.py`: `python -m app.cli` — projects | clips | export | channels | publish (with `--at`) | metricool
  (`tools` or a tool name + `--args`). Uses the app's data dir; keys from repo `.env` like dev.
- Tests: `tests/test_publish.py` (13) — fake Buffer GraphQL + fake auth.buffer.com + fake S3 host + fake MCP
  server (all local ThreadingHTTPServers; HTTP/1.1 + Content-Length required or httpx's pool chokes); the OAuth
  test drives the REAL loopback listener; SigV4 verified against an independently computed signature; OAuth token
  endpoints are form-encoded (the fake must parse both).

**After Phase C: the original M8 (refinement + packaging) still stands, plus real-key verification rounds.**

## Resume here (new chat — real-key verification, then M8)

1. `git log --oneline -1` + read this file + DECISIONS.md, then `npm test` once to confirm a green base.
2. Real-key verification round (nothing is committed yet — commit after this):
   - Clips (Phase B): real Groq + DeepSeek -> clip a real YouTube link end to end; yt-dlp bot-check on the live
     network; transcript cache hit on re-run; face-crop + caption quality on real footage.
   - Buffer (Phase C): register the user's OAuth app (public/PKCE) at developers.buffer.com with redirect
     `http://127.0.0.1:8787/callback`, paste client id in Settings, connect, add an R2 bucket, publish one clip
     now and one scheduled; verify Buffer actually fetches the video from the bucket URL.
   - Metricool (Phase C): paste the API key, Check connection, then use `python -m app.cli metricool tools` to
     see the real tool schemas and wire a proper "post via Metricool" mapping for schedule_post (today the RPC
     `publish.metricool_call` is a raw passthrough — the UI dialog only covers Buffer).
3. M8 (refinement + packaging: electron-builder NSIS + PyInstaller-frozen backend, bundled ffmpeg).

## User feedback round 2 (2026-09-20, implemented)
- **Video length control**: `brief.target_seconds` (Auto/~15/~30/~45/~60s) -> prompts.py writes narration to the
  target ("Narration target: about N seconds..."); render stays narration-driven.
- **Post-completion swaps**: Preview modal already redoes quote/narration/visual/design per piece; ADDED a
  **Narration voice** select in the modal -> `projects.set_voice` updates the brief and `jobs.start kind=render`
  now accepts `piece_ids` (renders.render_project filters) so only that piece re-renders.
- **Subtitle toggle** (social briefs, default off): `brief.subtitles` -> renders.py synthesizes word timings from
  the narration audio length (ponytail: proportional, not forced-aligned) and burns the clip-style karaoke ASS
  (Montserrat) via render_video(subtitles=). Real word-level alignment would need forced alignment later.
- **Look effects at creation**: `brief.look_filter` (none/warm/cool/mono/vivid -> colorbalance/eq/hue),
  `blur_background` (split + boxblur bg + sharp centred overlay), `parallax` (zoompan push-in on video pieces;
  stills always push in). All optional; default = clean natural render.
- **Auto-scroll**: Project + Clip pages scroll the finished list into view when the job completes.
- Watch out: ffmpeg filter graphs for the new effects are covered by a real render test in test_render.py
  (graph syntax mistakes fail there, not in a user render).

## Feature backlog / product direction (user-supplied 2026-09-20)

Ideas and requirements to revisit in future phases. Items 2 and 3 have base integrations from Phase C; the rest
is open. North star: **turn raw long-form content into polished, platform-ready short-form content with as
little manual editing as possible** — every feature should improve content quality, automation, publishing,
platform compatibility, user control, speed, reliability, cost efficiency, or professional appearance.

1. **IP detection / YouTube-compatible network routing** (backlog / research): detect the app's public IP,
   explore network configurations compatible with YouTube access (regional testing, download reliability);
   proxy/VPN support only if legitimate; never hard-code IP ranges; stay inside YouTube's ToS.
2. **Metricool** (integration, partially done): still open — inspect the real `schedule_post` MCP tool schema
   with a real key and build a proper "post via Metricool" UI mapping (today: raw passthrough via
   `publish.metricool_call` + CLI).
3. **Buffer** (integration, partially done): still open — real-key verification end to end (OAuth app
   registration with redirect `http://127.0.0.1:8787/callback`, R2 bucket, publish now + scheduled, confirm
   Buffer fetches the video from the bucket). Architectural principle that already holds: the app must not
   become the user's social-media credential store — OAuth only, DPAPI-encrypted tokens, retain the minimum.
4. **Premium short-form quality** (core product direction, continuous): clips must feel like premium modern
   Shorts, not automated clips — smart selection, strong hooks, dead-space removal, natural pacing, word-level
   karaoke captions inside platform safe areas, subject-tracked reframing with smooth movement, clean audio
   (noise reduction, balancing, music ducking), sparing transitions, professional typography. Priority order:
   story > hook > pacing > clarity > visual quality > audio quality > platform-safe composition > brand
   consistency. Never optimize for "looks AI generated."

## User feedback round (2026-09-20, implemented + pushed)
- **Create page**: Tone is a dropdown again (user prefers it); **Narration voice** picker (per-project
  `brief.voice` = "engine:voice", rendered by renders.py via `tts.get_tts(engine)`; `tts.voices` RPC lists
  Kokoro `get_voices()` + Windows SAPI names); **frame rate** choice 30/60 (`brief.fps`, also on clip briefs,
  honored via `render_video(out_fps=)` / `render_clip(fps=)`).
- **Rendered social videos are now clean** — no scrim, no quote text burned in (user decision). `render_video`
  takes scrim/quote/palette optionally; image (4:5) renders still carry the quote. Ctrl+Enter on Create moved to
  a window-level listener (form-level one died when focus was on body after using a dropdown -> React #310 fix
  came from moving the effect above the `if (!brief)` early return).
- Watch out: existing installs' stored settings keep `tts_provider: 'windows'` — the kokoro default applies to
  fresh installs/new settings rows; picking a Kokoro voice per project sidesteps it.
- M8 packaging started: `backend.spec` freezes the backend (232 MB one-folder, includes cv2/kokoro/yt-dlp +
  fonts/YuNet); electron-builder installed; NOT yet verified end to end (exe RPC/render check, NSIS build,
  backend.ts packaged branch: spawn `resources/backend/backend.exe` + bundled ffmpeg on PATH when packaged).

## Open decisions / notes
- Rail shows Dashboard, Create, Projects, Library, Queue, Exports (Queue/Exports landed with M6).
- Platform metadata adapters (PRD §69) landed with M6 export; pieces hold one metadata set, adapted per platform.
- Scoring weights are backend settings (`asset_weights`); user-facing knob is `asset_cooldown_days`.
- `video_image` renders both outputs per piece; instagram_feed targeting also renders the 4:5 image (M6).
- Palette text colour and brand clamps are hardcoded defaults (§24); per-user brand settings can come later.
- TTS swapped 2026-09-20: default is now **Kokoro** (82M int8 quantized, `kokoro-v1.0.int8.onnx` from the
  kokoro-onnx GitHub releases; `python -m app.tts download` fetches it + voices.bin; verified live). Windows SAPI
  stays as the zero-dep fallback. kokoro-onnx >= 0.6 flipped `create()` to sync — the code accepts both APIs.
  Existing settings rows keep their stored provider; the kokoro default applies to fresh installs.
- Clip open decisions to settle in-chat (Phase C): whether clip export should ALSO drive publishing directly from
  the clip's per-platform posts; whether rejected clips should be deletable on disk to reclaim space.
- ClipperAi's two-model selection (flash scan / pro picks) collapsed into the single `ai_model` setting — revisit
  if pass-2 copy quality disappoints with a cheap model.
- Smoke flakiness note: running heavy ffmpeg work in parallel with the smoke once killed the app window mid-run
  ("Target page... has been closed"); rerunning it alone passed. Run smoke standalone.
