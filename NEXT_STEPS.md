# Handover

Last updated 2026-11-07. This is the single source of truth for progress and next steps; `.claude/handover.md` is
the older milestone log (M1-M8) and is superseded where they disagree. Read this, then `.claude/CLAUDE.md`.

## Start here

- Branch `quality-motion-openrouter`, pushed through `ce2ca5a` (2026-11-07: render fix, footage review, project
  palette, deletes, curl_cffi, three.js background, motion system, page redesign, editing-skills pass; the earlier
  `e2d747c` went up with it). `npm test` green: 171 backend tests, typecheck, build, smoke. `main` is untouched.
- **Owner decisions that now bind every change are in `.claude/CLAUDE.md` "Owner decisions"** (splash locked, silk
  background, pick footage before download, one palette per project, everything deletable).
- Repo `.env` (gitignored) holds real `OPENROUTER_API_KEY` and `PEXELS_API_KEY`. Never print them. OpenRouter
  account limit is $4; well under $0.05 has been spent.
- The owner's real data (`data/app.db`) has a project "Communication; anyone can persuade" whose three renders
  failed on the now-fixed crash: re-render it as the first real check.
- Next real work: step 12 (render a real piece end to end, clip a real video). It now also checks the footage
  review with real Pexels results and the editing-skills pass by eye and ear.

## Render fix, footage review, project palette, deletes (2026-11-07, in `ce2ca5a`)

| Change | Where |
|---|---|
| **Render fix:** every render with animated titles on crashed (`'str' object has no attribute 'overlay_graph'`): a local `motion` (a shot's camera move) shadowed the motion module. Renamed `move`; `test_render_still_with_an_animated_layer` covers the path (the suite runs motion off, so nothing reached it). | `render.py`, `tests/test_render.py` |
| **Footage review (owner decision):** generation stores candidates (thumbnails only, under `media/candidates/`) with the AI's picks pre-selected in `content.review`; nothing full-size downloads. `visuals.pick` saves a piece's pick at once; the `visuals` job (`assets.download_picks`) downloads exactly the picks, refuses up front if a piece has none, and cleans previews no pending review still shows. Pre-picks follow the old rules (fresh first, look-alikes never pre-picked, exhausted pool falls back to least-used) and later pieces avoid earlier pieces' pre-picks. "Find another visual" proposes too; the old footage stays until confirmed. Render is disabled while footage waits. | `assets/__init__.py`, `content.py`, `jobs.py`, `components/FootageReview.tsx`, `pages/Project.tsx` |
| **One palette per project (owner decision):** built from every piece's hero colours interleaved; pieces confirmed later inherit the project's palette. | `assets._project_palette` |
| **Individual deletes:** Library assets (pieces that used one drop the shot; a piece left empty is told to find another visual), single pieces, single renders (piece drops to written), clips, exports (only that project's folders in the shared dated folder). All refused while a job runs on the project. | `assets.delete_asset`, `content.delete_piece`, `renders.delete`, `clips.delete`, `export.delete`, `jobs.ensure_idle`, `tests/test_delete.py` |
| **From the ClipperAi repo** (the owner's clipper; `Video-Agent` is empty): its engine was already ported and ours is ahead (glide crops, tightening, cold open, cleaned captions). Brought over `curl_cffi` so yt-dlp can impersonate a browser (Dailymotion refuses without it); added to `backend.spec` hiddenimports. Its job-level retry was not ported: our network calls already retry with backoff per call. | `requirements.txt`, `backend.spec` |

Verified: 171 backend tests, typecheck, build, smoke (now walks generate → footage review → confirm → render).
**Not verified:** a real Pexels search through the review screen; a packaged build with `curl_cffi` (run `npm run package` + `npm run smoke:packaged`).

## UI motion and redesign pass (2026-11-07, in `ce2ca5a`)

Owner asks, in order: three.js animation (CloudAI-X `threejs-skills`, installed in `.claude/skills/` and globally in
`~/.claude/skills/`), premium page/text/step transitions, a living splash, the wavy app background, title-bar fixes,
and a redesign of every page's cards. **The splash is owner-approved as is: do not change it.**

| Change | Where |
|---|---|
| `Ember.tsx`: plain three.js (React Three Fiber tried and dropped, 2 MB chunk). Layers: the CSS `.ambient` glows as a full-screen shader (a still frame equals the CSS), the ember **silk wave** (`wave` prop), rising embers. Moves only while `live`; the shell is live only while a job runs (`useBusy`, job.* events). Fresh canvas per mount (StrictMode reused a force-lost canvas and painted white in dev); context loss hides the canvas. | `components/Ember.tsx`, `lib/studio.ts useBusy` |
| Splash: living glow + embers, no wave (`wave={0}`), staged word-by-word entrance, exit into the studio. Waves video no longer shown. | `pages/Splash.tsx` |
| Motion system (motion-design skill, "Premium"): `--ease-premium` / `--ease-exit`; page exit 190 ms then entrance; headings reveal word by word (`Reveal` in ui.tsx, used by `PageHeader`); shell entrance; wizard steps slide by direction; drawn step bar. Containers holding glass animate transform only (opacity/filter on an ancestor breaks backdrop-filter). Reduced motion turns all of it off. | `styles/index.css`, `app/App.tsx go()`, `components/ui.tsx` |
| Title bar: fullscreen detected from window geometry as well as the main-process flag (the flag lags on Windows), main re-broadcasts after a settled resize. Fixes missing fullscreen controls and the status dot floating mid-bar. | `lib/studio.ts useFullScreen`, `electron/main.ts` |
| Redesign (redesign-existing-projects skill): `Cover` shows real output only (rendered 4:5 image, clip cover, or the piece's quote on a lit frame). Dashboard: greeting + one-sentence real activity, "Pick up where you left off" feature card, cover-tile grid, first-run welcome. Queue: pipeline tabs + cover cards + per-stage empty copy. Exports: fanned proof covers, demoted path, Copy confirms. Project: cover per piece (click to preview). Library: glass filter bar, full-bleed asset cards. Create: topic as working title, genre feel, lit frames, deliverables, platform chips. | `components/Cover.tsx`, `pages/*` |
| Backend for the cards: `projects.list` adds `rendered`, `cover`, `quote`; `queue.list` adds `cover`; `exports.list` adds `covers` (clip frames as fallback). | `projects.py`, `queue.py`, `export.py` |

Silk edges: MSAA on and the display's own pixel ratio (cap 2), mesh 360×200; at 1 CSS pixel without MSAA the fold
silhouettes stair-stepped on the owner's 1.5x display. Verified on a 1.5x frame crop.
Queue cards always show the piece's quote (it is its identity); Library cards keep the provider · type line.
**Verified 2026-11-07 20:05:** `npm test` green (160 backend tests, typecheck, build, smoke), screenshots reviewed.

Smoke note: the smoke window is a real window; clicks in it during a run (the owner exploring the UI) navigated
away mid-job and caused the two "render timeout" failures. Diagnostics proved no remount and no code path to the
Dashboard. Run the smoke with nobody touching its windows. The Dashboard heading check now matches the greeting.

## Editing-skills pass (2026-11-07, in `ce2ca5a`)

Learned from three skill repos and applied where they beat what we had. Sources and licences:
`appariciojunior/video-editor-skills` (CC BY-NC 4.0: ideas and numbers only, no text copied),
`vyralcontent/content-skills` (MIT), `AgriciDaniel/claude-shorts` (MIT, its segment-scoring rubric), and the
`zhuyansen/awesome-claude-video-skills` index (nothing taken directly).

| Change | Why (the lesson) | Where |
|---|---|---|
| Long pauses are shortened to 0.3 s of air (40% after / 60% before), only past 0.5 s; was cut to 0.24 s past 0.35 s | Cuts with no breath "pop"; 0.5/0.3 was the setting real viewers liked for talk content | `clipper/tighten.py` |
| A pause is cut only if 85% of it is silent on the waveform (ffmpeg `silencedetect`, -43 dB, 0.25 s); fillers count as silence | Whisper gaps can hide a laugh or a missed word; cutting there clips speech. No silence found at all (music bed) = trust words, as before | `clipper/ff.py silences`, `tighten.keep` |
| Jump cuts alternate 100% / 107.5%; the cold open is pushed in to 115% for that line only; the clip opens at 100% | A jump cut with no framing change reads as a glitch; a push-in held past its line drags | `tighten.plan` (returns ranges + zooms), `render_clip.py` |
| Captions drop fillers, cut-off words ("es-") and doubled words ("I I"), keeping "that that"/"had had" | Captions are for reading, not a court transcript | `clipper/captions.py readable` |
| Clip pass 1 scores with a weighted rubric (hook 30, stands alone 25, emotion 20, value 15, payoff 10), drops < 60, prefers 25-45 s | Explicit criteria make the fast model's scores comparable | `clipper/select.py PASS1` |
| Clip hooks complement the first spoken line and name the payoff's kind; no vague teases, commands or wordplay. Posts: one ask (save / send to a named kind of person / comment with a stance), never "follow for more", "tag a friend" | Hook and CTA anti-patterns from content-skills | `select.py PASS2` |
| Written pieces: same hook anti-patterns, "but/so, never and then" lines, a turn a third of the way in, a looping last line; captions end on one fitting ask | Retention structure from content-skills | `creative/prompts.py` |
| Hashtags capped at 5, deduplicated, generic tags (#fyp #viral #explore ...) dropped; YouTube gets `#Shorts` first | Hashtags are labels, not reach; `#Shorts` marks Shorts-feed eligibility | `platforms/__init__.py tags` |

Not taken (on purpose): music bed envelope (our sidechain duck already does it), Resolve/Premiere scripting,
Remotion overlays (licence, see "Not doing"), literal foley (the skill found it cheesy too). Worth doing after
step 12 if footage shows the need: hook A/B variants (step 19), a punch-in on one mid-clip payoff line, a soft
riser into the cold-open cut.

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
| A | Merge `quality-motion-openrouter` into `main` (PR or direct); everything is committed and pushed | Owner's go-ahead to merge |
| 12 | Real-footage verification (below), starting with re-rendering the owner's failed project | The owner; a video for the clip half (a local file avoids YouTube's bot check) |
| 12b | Real Pexels search through "Choose the footage": thumbnails load, picks swap, only picks download, one palette across the batch | Step 12 |
| P | `npm run package` + `npm run smoke:packaged` to prove `curl_cffi` and the new UI survive freezing | Owner's go-ahead (long build) |
| 11 | Tune `creative/prompts.py` from step 12 output (callouts: only times, counts, turning words; never decoration) | Step 12 |
| 3 | Code signing, the fix for Avast sandboxing every new build | A signing certificate |
| 4 | Clean install test with no Avast exception | Step 3 |
| — | Read GSAP's licence (Webflow "Standard no charge", not open source) before shipping; HyperFrames also accepts WAAPI/Anime.js (MIT) | Owner |
| — | Simplify navigation (7 rail icons to 4: Home, Create, Library, Settings; Queue as a tray, Exports per project), proposed 2026-11-07 | Owner's yes on moving pages |
| — | Small polish seen in review: "Used before" also marks footage only pre-picked by another piece of the same batch; `src/assets/splash.webm` is unused (delete?) | Owner |
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
