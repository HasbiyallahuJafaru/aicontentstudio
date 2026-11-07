# Handover

Last updated 2026-11-07. This is the single source of truth for progress and next steps; `.claude/handover.md` is
the older milestone log (M1-M8) and is superseded where they disagree. Read this, then `.claude/CLAUDE.md`.

## Start here

- Branch `quality-motion-openrouter`, pushed. Last commit `50a4309` (steps 1-11, 15-18). `main` is untouched.
- **About 24 files are uncommitted** (Dashboard landing, Gemini TTS, plain Settings, Clear content, fullscreen
  controls; list below). `npm test` was green on them (155 backend tests, typecheck, build, smoke). Commit them
  first; the owner asked for commit + push of earlier work, so ask before pushing these.
- Repo `.env` (gitignored) holds real `OPENROUTER_API_KEY` and `PEXELS_API_KEY`. Never print them. OpenRouter
  account limit is $4; well under $0.05 has been spent.
- Next real work: step 12 (render a real piece and clip a real video). It needs a video from the owner.

Uncommitted files: `NEXT_STEPS.md README.md`, backend `app/{config,motion,renders,rpc,settings,tts,storage*}.py
backend.spec requirements.txt tests/{__init__,test_render,test_storage*}.py`, desktop `electron/{main,preload}.ts
scripts/smoke.mjs src/{app/App,components/Preview,components/ui,layouts/Shell,lib/studio,pages/Create,pages/Settings}`
(* = new).

## Run and test

```bash
npm run setup           # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev             # Electron + Vite HMR + Python auto-restart
npm test                # backend unittest + typecheck + build + smoke (fake servers, no paid calls), ~4 min
npm run package         # freeze backend, bundle ffmpeg, NSIS installer in apps/desktop/release (~321 MB, less now)
npm run smoke:packaged  # launches the built exe, checks every exe's signature, renders a motion layer
```

- Tests run keyless and motion-off: `tests/__init__.py` sets `ACS_NO_DOTENV=1` (never load the real `.env`) and
  `ACS_NO_MOTION=1`; `test_motion.RealRender` turns motion on and needs Edge.
- Real-key manual runs: point `ACS_DATA_DIR` at a throwaway folder and call backend modules directly from
  `apps/backend` (the `.env` loads automatically outside tests).
- PowerShell 5 is the shell: no `&&`; `Set-Content -Encoding utf8` writes a BOM (strip it); multi-line git commit
  messages must go through `git commit -F <file>` (a here-string piped to `-F -` became file arguments and
  committed nothing). Git identity is set repo-local to `HasbiyallahuJafaru <jafaruhasbiyallahu@gmail.com>`.

## What the app is now (changes this session)

| Area | Now | Where |
|---|---|---|
| Keys | One `OPENROUTER_API_KEY` for every AI call (writing, clip selection, transcription, narration) + `PEXELS_API_KEY`; Unsplash optional; Metricool optional. DeepSeek/Groq keys removed. | `creative/model.py` (`BASE`, `api_key`), `electron/secrets.ts` |
| Writing | `deepseek/deepseek-v4-pro` writes plans, pieces (+metadata), clip picks, post copy; `deepseek/deepseek-v4.1-flash` scans transcripts (clip pass 1). Requests send `provider.require_parameters` (JSON-mode providers only). Bare legacy names map to OpenRouter ids. | `settings.py`, `clipper/select.py` |
| Transcription | `openai/whisper-large-v3-turbo` via OpenRouter, 300 s chunks (60 s upstream limit). Segment-estimated words if a provider returns none. | `clipper/transcribe.py` |
| Narration | Gemini TTS `google/gemini-3.8-flash-tts` via `/audio/speech`. Gemini only returns PCM (rate/channels in the content type), wrapped as WAV with stdlib `wave`. 18 voices, default Charon, picked per project; the piece's `delivery` becomes `instructions`. Kokoro/Windows voices and all `tts_*` settings removed. | `tts.py`, `renders.py` |
| Clips | Dead air (>0.35 s) and fillers cut; optional cold open plays the strongest line first; captions retimed; group pop + yellow spoken word + orange keywords; small crop moves glide, big ones cut; master medium/CRF 18/192k; YouTube cookies setting. | `clipper/{tighten,render_clip,captions,crop,select,acquire}.py` |
| Motion | HyperFrames (Apache 2.0) renders an animated hook title and timed callouts as alpha WebM through Edge/Chrome, run on the app's own Electron binary as Node; ffmpeg composites them. Cached by content. Never fails a job. | `motion.py`, `motion_assets/{hook,callout}.html`, `apps/desktop/motion/render.mjs` |
| Packaging | Frozen backend is `AI Social Content Studio Engine.exe` with icon + version info, UPX off; `motion/` + `node_modules/` unpacked from the asar. Signing switches on with a cert (see step 3). | `backend.spec`, `apps/desktop/package.json` |
| UI | Splash opens the Dashboard. Create's topic suggestions open on click/typing, not on autofocus. Settings: API keys, AI (two model dropdowns, price-tier labels), Video (quality preset, animated titles, music file), Storage (space used, Open folder, **Clear all content**), Advanced collapsed (Publishing, YouTube cookies). Content defaults removed. | `pages/Settings.tsx`, `App.tsx`, `components/ui.tsx` |
| Storage | `storage.usage` / `storage.clear`: deletes all projects and assets (cascades), wipes the media folder, VACUUMs; keys and settings stay; refuses while a job runs. | `storage.py` |
| Window | Maximize means fullscreen. In fullscreen the bar draws minimize / restore / close flush top-right (Windows hides its own). `useFullScreen` re-checks on resize because `enter-full-screen` doesn't reliably fire when entered from the maximize handler; the handler un-maximizes first so Restore doesn't bounce back. | `electron/main.ts`, `layouts/Shell.tsx`, `lib/studio.ts` |

## Real-key results so far (2026-11-07)

- Transcription: real word-level timings back from OpenRouter (14 words, accurate pauses), $0.00002.
- Narration: Gemini TTS answered (5 s of speech in 5.8 s); unknown voice names are a 400, so only listed ones are
  offered.
- Writing: one piece per genre with the pro model, 60-100 s each; one malformed reply repaired automatically.
  Hooks are strong ("The *Lie* You Whisper Alone", "*Only You* Know"); attributed genres quoted Epictetus and
  Marcus Aurelius. Weak spots for prompt tuning: some callouts are filler ("mile two", "reluctant"); multi-word
  callout anchors now land on their first word.
- Pexels key valid (24,999 requests left this month).

## What is left, in order

| # | What | Waiting on |
|---|---|---|
| A | Commit the uncommitted work; merge `quality-motion-openrouter` into `main` (PR or direct) | Owner's go-ahead to push/merge |
| 12 | Real-footage verification (below) | A video from the owner (local file avoids YouTube's bot check) |
| 11 | Tune `creative/prompts.py` from step 12 output (callouts: only times, counts, turning words; never decoration) | Step 12 |
| 3 | Code signing, the fix for Avast sandboxing every new build | A signing certificate |
| 4 | Clean install test with no Avast exception | Step 3 |
| — | Read GSAP's licence (Webflow "Standard no charge", not open source) before shipping; HyperFrames also accepts WAAPI/Anime.js (MIT) | Owner |
| 13, 19 | Speaker-aware crop; model-written motion, sound design, hook A/B variants | Step 12 showing the need |

### 12. Real-footage verification
- [x] Transcription word timings, writing per genre, TTS call, Pexels key (above).
- [ ] Render one real written piece end to end (Pexels footage, Gemini narration, captions, grade, animated hook
      and callouts). Judge it frame by frame and by ear; note time per video with motion on.
- [ ] Clip a real video: dead-air cuts land between words with no clicks; the cold open is a real payoff line;
      caption pop and keyword colours; reframing glides vs cuts; the animated hook.
- [ ] Buffer: connect, publish now, publish scheduled. Metricool: inspect `schedule_post`, then wire the UI.

### 3. Code signing (ready, waiting on a certificate)
- Azure Trusted Signing only takes individual developers in the US/Canada (organizations US/Canada/EU/UK);
  elsewhere an OV certificate (Certum, SSL.com).
- Every shipped exe (app, engine, ffmpeg, ffprobe, esbuild, uninstaller, installer) already goes through
  electron-builder's signing hook. Switch on by cert type:
  - `.pfx`: set `CSC_LINK` + `CSC_KEY_PASSWORD`, then `npm run package`. No config change.
  - USB token / cloud cert in the Windows store: `"signtoolOptions": { "certificateSubjectName": "<Issued to>" }`
    under `build.win` in `apps/desktop/package.json`.
  - Azure: `"azureSignOptions": { publisherName, endpoint, codeSigningAccountName, certificateProfileName }`
    + `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.
- Done when `ACS_REQUIRE_SIGNED=1 npm run smoke:packaged` passes.

### 4. Clean install test
Remove both exes from Avast's exceptions (Menu, Settings, General, Exceptions), install the signed build, run a
full generate and clip. If Avast still sandboxes the engine: report a false positive, then rebuild the PyInstaller
bootloader from source.

### 13. Speaker-aware crop (only if two-person podcasts crop the wrong face)
WhisperX + pyannote diarization (Hugging Face token + model licences), word -> speaker -> face.

### 19. Motion, later
Model-written compositions checked by `hyperframes lint`; CC0 whoosh/riser; hook A/B variants. Batch layers per
video into one browser launch if motion time adds up (~40 s for hook + callout today, first launch dominates).

## Gotchas learned this session

- **Avast AutoSandbox** sandboxes every new unsigned exe hash on first run, the app and the engine separately (that
  was the "two apps" symptom). Expect the first launch after any rebuild to time out (packaged smoke, manual runs);
  the second passes. Signing is the fix. Windows Defender has no detections.
- **HyperFrames templates:** never declare a global named `top` (it is `window.top`): the script dies and the layer
  renders fully transparent with no error. Size/duration go into the markup (`__W__`, `__H__`, `__DUR__`), not JS.
  The browser comes from `HYPERFRAMES_BROWSER_PATH`, ffmpeg from `HYPERFRAMES_FFMPEG_PATH` (not `chromePath`).
- **Puppeteer's Chrome download** stays blocked by npm's allow-scripts; the app uses Edge. Keep it blocked.
- **Gemini TTS** rejects `mp3`; only `pcm`. OpenRouter ignores provider routing for transcription.
- **Render speed:** written-content renders keep `-preset veryfast` (medium more than doubled render time for mostly
  smaller files); CRF sets quality. Clips use medium (light filter graph).
- **Smoke timing:** Export waits for the whole re-render job (`click({ timeout: 240_000 })`); on the project page
  "Projects" matches both the rail button and the back link, so don't navigate by that name there.
- Saved settings rows from older installs keep stale fields (`tts_*`, old CRF 22); pydantic ignores unknown keys.

## Earlier steps (done, for reference)

1-2 backend identity + Avast diagnosis; 5-10 clip quality; 11 + 11b writing model split and one OpenRouter key;
15-18 HyperFrames motion graphics; this session's UI/TTS/storage changes. Commit `50a4309` message has the detail.

## Not doing

- Nuitka/Tauri or merging Python into Electron: signing fixes the antivirus problem for far less.
- A local LLM (Ollama) or local TTS: one OpenRouter key is simpler and better; Kokoro was removed on purpose.
- Remotion (source-available, paid above a small company size). An end card with the quote (the owner removed
  quote text from videos on 2026-09-20).

The ceiling for written videos is stock footage; better search queries help, no edit grammar replaces a real shoot.
