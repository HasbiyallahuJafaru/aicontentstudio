# Next Steps

Work in order. Each step lists what to change, where, and how to know it is done. Finish a step and confirm
`npm test` is green before starting the next. Diagnosis behind this list: 2026-11-07.

---

## Phase 1: One app, not two

The antivirus problem. On this machine Windows Defender has no detections. Avast AutoSandbox is the one acting:
the main exe only runs normally because it is on Avast's exception list, and the uninstaller was sandboxed
(`autosandbox.log`, 2026-09-26). Nothing is signed, and the backend is an anonymous `backend.exe`.

### 1. Give the backend an identity (done 2026-11-07)
- [x] Rename the frozen exe to `AI Social Content Studio Engine.exe` (`ENGINE` in `apps/backend/backend.spec`).
- [x] Add the app icon and a version resource (read from `apps/desktop/package.json`) to `EXE(...)`.
- [x] Set `upx=False` explicitly in `EXE(...)` and `COLLECT(...)`.
- [x] Update the spawn path in `apps/desktop/electron/backend.ts` and the check in `scripts/smoke-packaged.mjs`.
- Verified: the exe reports FileDescription, ProductName, CompanyName and version 0.1.0; `npm test` green
  (135 backend tests, typecheck, build, smoke); `npm run smoke:packaged` passes.

### 2. Reproduce the "separate apps" symptom (done 2026-11-07)
- [x] Launched the fresh unpacked build. Avast `autosandbox.log`:
  - 14:52:31 `AI Social Content Studio.exe` -> `Sandboxing`
  - 14:52:59 `AI Social Content Studio Engine.exe` -> `Sandboxing`, separately: this is the split
  - 14:53 onward both -> `Not sandboxing (because the file is in the exception list)`
- Cause: unsigned exes with a new hash get sandboxed on first run, each one on its own. Every rebuild is a new
  hash, so every new unsigned build gets sandboxed again. The first packaged-smoke launch timed out for this
  reason; the second passed.

### 3. Code-sign everything (ready, waiting on a certificate)
- [ ] Get a signing identity. Azure Trusted Signing only accepts individual developers in the US/Canada
      (organizations: US/Canada/EU/UK). Elsewhere, an OV certificate (e.g. Certum, SSL.com) works.
- [x] The engine, `ffmpeg.exe`, `ffprobe.exe`, the Electron exe, the uninstaller and the installer all go through
      electron-builder's signing hook (confirmed in the build log). No config change needed for a .pfx.
- [x] `npm run smoke:packaged` prints the signature status of every shipped exe; `ACS_REQUIRE_SIGNED=1` makes
      any unsigned exe fail it.
- How to switch it on, by certificate type:
  - **.pfx file:** set `CSC_LINK=<path to .pfx>` and `CSC_KEY_PASSWORD=<password>`, then `npm run package`.
  - **USB token or cloud cert in the Windows certificate store (most OV/EV certs today):** add
    `"signtoolOptions": { "certificateSubjectName": "<Issued to name>" }` under `build.win` in
    `apps/desktop/package.json`.
  - **Azure Trusted Signing:** add `"azureSignOptions": { "publisherName", "endpoint",
    "codeSigningAccountName", "certificateProfileName" }` under `build.win`, and set `AZURE_TENANT_ID`,
    `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.
- **Done when:** `ACS_REQUIRE_SIGNED=1 npm run smoke:packaged` passes.

### 4. Clean install test (blocked on step 3)
- [ ] Remove both app exes from Avast's exception list (Avast -> Menu -> Settings -> General -> Exceptions).
- [ ] Install the signed build and run a full generate and a full clip.
- [ ] If Avast still sandboxes the engine, report it to Avast as a false positive. If it persists after that,
      rebuild the PyInstaller bootloader from source.
- **Done when:** a clean install runs with no exception list entry and no sandbox.

---

## Phase 2: Clip quality (no new dependencies)

Steps 5-10 implemented 2026-11-07. `npm test` green (142 backend tests, typecheck, build, smoke). Still needs a
real-footage review: none of this has been judged on a real podcast or YouTube link yet (that is step 12).

### 5. Better master encode (done)
- [x] Clips (`clipper/render_clip.py`): `-preset medium -crf 18`, audio 192k.
- [x] Written-content renders (`render.py`): default CRF 22 -> 18 (`settings.py`). The preset stays `veryfast`:
      `medium` pushed the smoke render past 240 s (vs 98 s) for mostly a smaller file. Installs that already
      saved settings keep their stored CRF; set Render -> Quality to 18 in Settings.

### 6. Dead-air and filler removal (done)
- [x] `clipper/tighten.py`: `keep()` cuts pauses over 0.35 s down to 0.12 s of breath each side and drops
      unambiguous fillers (um, uh, er, hmm...). "like"/"you know" are left alone (they need context).
- [x] `render_clip.render(ranges=...)` trims each range, crops each one to the face, joins with 10 ms audio
      fades, and the captions are retimed onto the joined timeline (`tighten.retime`).

### 7. Cold-open hook (done)
- [x] Pass 2 in `clipper/select.py` may return `cold_open_start/end`: the clip's strongest line when it is not
      already the opening. Accepted only inside the clip, 0.8-4.5 s long, and at least 1.5 s after the start.
- [x] It plays first (padded, tightened), then the clip runs from the top.

### 8. Animated captions (done)
- [x] Each word group pops in (82% -> 100% over 120 ms); the spoken word is yellow; the model's 2-6 `emphasis`
      words are orange. Colours reset with `\c`, not `\r` (which would reset the pop's scale). Frame-checked.
- [x] Position unchanged: bottom margin 560/1920, clear of TikTok/Reels UI.

### 9. Smooth reframing (done)
- [x] `crop.position_expr`: moves under half a crop width glide over 0.5 s (smoothstep); bigger moves (a
      different speaker) still hard-cut.

### 10. YouTube downloads (done)
- [x] Settings -> Clip downloads -> YouTube cookies: a browser name (firefox works best; Chrome/Edge often
      lock their cookies on Windows) or a cookies.txt path. `ytdlp_cookies` in `settings.py`.
- [x] Bot-check and cookie-read failures give human errors that point to that setting.

---

## Phase 2b: Motion graphics with HyperFrames

Feasibility proven 2026-11-07: `@hyperframes/producer` 0.9.20 (Apache 2.0) rendered a 3 s 1080x1920 kinetic hook
title through the Edge that ships with Windows (`HYPERFRAMES_BROWSER_PATH`), to VP9 WebM with real alpha, and the
app's ffmpeg composited it over footage cleanly. Measured cost: 30 s to render 3 s (90 frames, 3 workers, screenshot
mode; Windows has no BeginFrame). That decides the shape: HyperFrames renders only the motion-graphics moments
(hook title, callouts, end card) as alpha layers; the existing ffmpeg edit stays the base. A full 60 s video through
HyperFrames would take ~10 min per piece.

Steps 15-18 built 2026-11-07. `npm test` green (152 backend tests incl. a real Edge render, typecheck, build,
smoke with a motion hook rendered inside the app); `npm run smoke:packaged` renders a motion layer with the
installed exe. Not yet judged on real footage or real model output (step 12).

### 15. Engine in the app (done)
- [x] `@hyperframes/producer` 0.9.20 in `apps/desktop` (Puppeteer's Chrome download stays blocked by npm's
      allow-scripts); `apps/desktop/motion/render.mjs` renders one composition dir to an alpha WebM.
- [x] The backend runs it with the app's own Electron binary as Node (`ACS_NODE` + `ACS_MOTION_RUNNER` from
      `backend.ts`, `ELECTRON_RUN_AS_NODE=1`); dev falls back to `node` on PATH.
- [x] Browser: `HYPERFRAMES_BROWSER_PATH`, else Edge, else Chrome; ffmpeg: the bundled one.
- [x] Packaging: `motion/` and `node_modules/` unpacked from the asar. Installer 296 -> 321 MB. Ships an
      `esbuild.exe` (a HyperFrames core dependency): unsigned like the rest until step 3.

### 16. Template library (done)
- [x] `apps/backend/app/motion_assets/`: `hook.html` (bar draws, words rise one by one, *keywords* in the accent
      colour bounce, lifts away at 2.3 s) and `callout.html` (a phrase or number punches in, holds, drops out).
      Accent and case per genre (`motion.LOOKS`); Montserrat ExtraBold bundled for identical renders.
- [x] Probe collision fixed: keywords bounce instead of scaling, so neighbours never overlap.
- Skipped: end card. The user removed quote text from videos (2026-09-20); an end card would put it back.
- Skipped: HyperFrames registry blocks (licence check first; not needed for the hook/callout).
- Found and fixed: a template global named `top` (it is `window.top`) killed the script and rendered a fully
  transparent layer with no error. `test_motion.RealRender` now checks the words are opaque mid-animation.

### 17. AI direction (done)
- [x] Clips: pass 2's `hook` is now the animated title, 1-2 keywords in `*asterisks*` (stripped before storing).
- [x] Written pieces: new optional `hook` (shown with the sound off, so a sharper promise than the first line)
      and 0-2 `callouts`, each tied to a narration word and placed at that word's real timing. Old pieces load.

### 18. Compositing and controls (done)
- [x] `motion.overlay_graph` composites layers (libvpx decode keeps alpha, `setpts` places each one);
      used by `render_clip.py` and `render.py`. Layers are cached by content: re-renders reuse them.
- [x] Settings -> Render -> Motion graphics on/off. Off, no browser, or a failed layer = the plain edit; motion
      never fails a job. The test suite runs with it off (`ACS_NO_MOTION`), except `test_motion`.
- Cost measured: ~40 s for a hook + callout on this laptop (first launch of the browser dominates); cached
  repeats are instant. ponytail: one browser launch per layer; batch layers per video if it adds up.

### 19. Later, only if 15-18 land well
- Model-authored compositions checked by `hyperframes lint` before rendering.
- Sound design (CC0 whoosh/riser) and hook variants for A/B testing.

Open questions: GSAP 3.15 uses Webflow's "Standard no charge" licence, not an open-source one; read it before
shipping (HyperFrames also accepts WAAPI and Anime.js, MIT). Edge launched headless from the app may draw Avast's
attention like the engine did; signing (step 3) covers our exes, Edge is already signed by Microsoft.

---

## Phase 3: Written-content quality

### 11. Stronger writing model (built 2026-11-07, quality unjudged)
- [x] `ai_model` (writing: plans, pieces with their metadata, clip picks and post copy) now defaults to
      `deepseek-v4-pro`; new `ai_model_fast` (`deepseek-flash`) only scans whole transcripts in clip pass 1.
      Metadata is written in the same call as the piece, so there is no separate metadata step to put on flash.
- [x] Default max tokens 4000 -> 8192: both models think by default, and thinking spends the same budget.
- [x] Settings -> AI shows Writing model and Scanning model. Test pins pass 1 = fast, pass 2 = writer.
- Names confirmed on api-docs.deepseek.com (2026-11-07). Pro costs about 4.4x flash for input and 3.3x for
  output: fractions of a cent per piece.
- Existing installs keep their saved `deepseek-flash`: change Writing model to `deepseek-v4-pro` in Settings.
- [ ] Generate one batch per genre with a real key and tune `apps/backend/app/creative/prompts.py`.
- **Done when:** a blind read of pro vs flash output picks pro.

### 11b. One AI key: OpenRouter (done 2026-11-07)
- [x] The DeepSeek and Groq keys are gone. `OPENROUTER_API_KEY` covers writing, clip selection and transcription
      (`creative/model.py` `BASE`/`api_key`, `clipper/transcribe.py`). Pexels stays (stock media, not AI);
      Unsplash is optional.
- [x] Chat requests send `provider.require_parameters` so OpenRouter only routes to JSON-mode providers.
- [x] Transcription: `openai/whisper-large-v3-turbo` (~$0.012/audio hour via DeepInfra, ~$0.04 via Groq;
      OpenRouter picks the provider). Chunks 600 s -> 300 s for OpenRouter's 60 s upstream timeout. If a provider
      returns no word times, words are estimated inside each segment instead of failing.
- [x] Saved bare model names (`deepseek-flash`) map to OpenRouter ids on load.
- Existing installs: the old DeepSeek/Groq keys stay in the encrypted file but are no longer read. Add the
  OpenRouter key in Settings.
- **Unverified until a real key:** that the transcription provider OpenRouter picks returns word timestamps.

### 12. Real-key verification (from `.claude/handover.md`)
Put `OPENROUTER_API_KEY` and `PEXELS_API_KEY` in the repo `.env` (gitignored), or add them in Settings.
- [ ] Writing: one batch per genre.
- [ ] Pexels: real searches, check the shot pool variety.
- [ ] Clips: a real YouTube link end to end (download, transcription with word times, crop, captions).
- [ ] Buffer: connect, publish now, publish scheduled.
- [ ] Metricool: inspect the `schedule_post` tool, then wire the UI.

---

## Phase 4: Only if needed

Do these only when the earlier phases show the need.

### 13. Speaker-aware crop
Only if most clip sources are two-person podcasts and the crop picks the wrong face.
- [ ] Add WhisperX + pyannote diarization (needs a Hugging Face token and accepting the model licences).
- [ ] Map each word to a speaker, each speaker to a face, and crop to whoever is talking.

### 14. Expressive narration
Only if a listening test says Kokoro is too flat.
- [ ] Blind test Kokoro against Chatterbox (MIT) on the same three scripts.
- [ ] If Chatterbox wins, add it as an optional download (it needs PyTorch, several GB). Keep Kokoro as the default.

---

## Not doing

- Moving to Nuitka or Tauri, or merging Python into Electron: signing fixes the antivirus problem for far less.
- A local LLM via Ollama: DeepSeek is cheap and writes better.
- MediaPipe, Dia, Sesame CSM: either they only add a dependency for something the app already covers, or they
  are too slow for local narration.

The ceiling for written videos is stock footage. Better search queries help; no edit grammar makes repeated
stock clips look like a real shoot.
