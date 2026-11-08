# AI Social Content Studio: project instructions

Windows desktop app that turns a short brief into finished social videos/images (quote, narration, visuals, palette,
TTS, FFmpeg render, per-platform metadata) and exports them for Metricool. Local only: no accounts, no cloud.

- Spec (source of truth for scope and phase order): `Prd.txt`. Product record: `PRODUCT.md`.
- Dependency/license decisions + machine gotchas: `DECISIONS.md` (update when a dependency changes).
- **Progress and next steps: `NEXT_STEPS.md` (repo root). Read it first in every new chat, and update it at the
  end of every phase (or before the chat runs out).** `.claude/handover.md` is the older M1-M8 log.

## Developer identity (for branding + integrations)
- Website: https://hasbiyallahu.xyz · GitHub: https://github.com/HasbiyallahuJafaru ·
  LinkedIn: https://www.linkedin.com/in/hasbiyallahu-jafaru/ · Instagram: TBD (user will supply).
- "Created by" footer (interactive SVG logos for website/LinkedIn/GitHub) goes on every Shell page, and the splash
  gets Instagram+GitHub icons lower-left — see handover Milestone 7 Phase A.

## Product direction (user priority)
North star: turn raw long-form content into polished, platform-ready short-form content with as little manual
editing as possible. Clip quality bar: premium modern Shorts, never "AI-generated looking" — priority order:
story > hook > pacing > clarity > visual quality > audio quality > platform-safe composition > brand consistency.

**Content taxonomy = genres, not tones** (researched against top performers 2026-09-20): Hope (hopecore spoken
word, soulsigh-style), Hard Truth (Goggins/Jocko speech edits), Stoic Wisdom (Daily Stoic), Historical Voices and
Book Wisdom (real attributed public-domain quotes only — modern books are copyrighted, keep it pre-1929), and
Cinematic Minimal (Mateusz M). Each genre's quote style and narration voice live in `app/creative/prompts.py GENRES`. Since 2026-11-08 there
are two writers: QUOTES_SYSTEM for quote images (quotes only, no narration/hook/shots; `PieceContent.narration` is
None) and VIDEO_SYSTEM for narrated shorts (`VideoPieceContent` requires narration). Both open with TOPIC_RULES: the
topic read literally is the brief, the planner writes a one-line `reading` that every piece is written against, and
clock-time/alarm/self-help-scene openers are banned unless the topic asks. Never reintroduce a fixed scene recipe.

**Output bar — renders must look EDITED, never plain:** multi-shot timelines (2-3 cuts from the asset with
alternating zoom-in / pan / zoom-out motion), a still cutaway merged between video shots, the genre's color
grade (`brief.look_filter`, default `auto` = genre grade), film dressing (vignette + grain), loudnorm narration,
optional karaoke subtitles (`brief.subtitles`). Quote text is NOT burned into videos (user decision). Rendering
belongs to `render.py render_video(shots=...)`; renders.py builds the shot plan in `_shots_for`.
Stills are art-directed designs in `app/design.py` (seven designs, bundled OFL fonts, typographic rules in its
docstring); subtitles are styled by `CaptionStyle` in `app/clipper/captions.py`. Never fall back to plain text on a scrim.

Backlog + integration statuses (IP routing research, Metricool/Buffer open items) live in
`.claude/handover.md` under "Feature backlog / product direction". Publishing integrations must stay OAuth-based
and store the minimum credentials (never a social-media credential store); the app stays local and free.

## Save tokens (user priority)
Don't read `Prd.txt` or big files end to end. Look things up with graphify, then read only the lines it points to:
```bash
graphify query "where are API keys stored?" --budget 1500
graphify explain "createBackend"
graphify path "Create.tsx" "projects.py"
graphify update .        # rebuild the map after code changes (~seconds, no AI calls, respects .gitignore)
```
For the PRD, grep its section headings (`grep -n "^# " Prd.txt`) and read just the section needed.
Skip long design ceremonies; one screenshot review round per UI phase.

## Layout
- `apps/backend/` Python 3.12 (stdlib + pydantic). `main.py` → `app/rpc.py` (method table `METHODS`), one module per
  area (`projects.py`, `settings.py`, `content.py`, `assets/`, `visual.py`, `tts.py`, `render.py`, `renders.py`,
  `export.py`, `queue.py`, `platforms/`), `app/assets/fonts/` (bundled Sora, OFL), `app/migrations/NNN_*.sql`,
  `tests/`. `app/clipper/` is the long-video → shorts engine, ported from the user's GitHub repo
  `HasbiyallahuJafaru/ClipperAi` (`apps/backend/clipper.py`, `downloader.py`; the user may call it "YTClipper";
  the local clone is gone, copying code is fine). Ours is ahead of it as of 2026-11-07 (glide crops, tightening,
  cold open, cleaned captions); check it for anything new before reinventing clipper features.
- `apps/desktop/` Electron + React. `electron/main.ts` (window, IPC allowlist, media:// protocol),
  `electron/backend.ts` (spawn/supervise Python), `electron/secrets.ts` (safeStorage), `electron/preload.ts` (the
  only renderer API: `window.studio`), `src/lib/studio.ts` (typed calls, hooks, shared constants),
  `src/components/ui.tsx` (all primitives), `src/components/Preview.tsx` (piece preview + regenerate/approve),
  `src/components/Branding.tsx` (developer socials + created-by footer), `src/components/Ember.tsx` (three.js
  living background, unmounted since the white redesign), `src/components/Cover.tsx` (real-output
  cover tiles), `src/components/FootageReview.tsx` (pick footage before download), `src/pages/*` (Splash first,
  then `Setup.tsx` whenever the OpenRouter or Pexels key is missing, then the Shell pages incl. Queue + Exports),
  `src/styles/index.css` (design tokens + the motion system).
- `apps/site/` the public landing site **ytclipper.xyz** (Vite + plain TS + three.js, no framework): `index.html` +
  four legal pages (privacy, terms, license, open-source; generated by `scripts/make-legal.py`), `src/hero.ts` (the
  film-strip three.js hero), `scripts/prepare-assets.py` (copies real renders/screenshots/icon out of the app).
  Brand on the web is "YT Clipper - AI Content Studio"; the installed app's productName is still "AI Social Content
  Studio" (owner has not asked to rename the app).
- `apps/download-worker/` Cloudflare Worker `ytclipper-download`: verifies a Turnstile token, then streams the
  installer from the private R2 bucket `ytclipper-releases`. The only sanctioned download path.
- `.claude/skills/threejs-*` (CloudAI-X threejs-skills, MIT; also installed globally): read the relevant one
  before touching `Ember.tsx` or `apps/site/src/hero.ts`.

## Release and deploy (2026-11-08)
- **Installer:** freeze the backend (`apps/backend/.venv/Scripts/pyinstaller backend.spec --noconfirm`), make sure
  `apps/desktop/resources/ffmpeg` holds the gyan.dev **essentials** build (`ACS_FFMPEG_DOWNLOAD=1 node
  scripts/fetch-ffmpeg.mjs` after removing the folder; the PC's full build makes a 315 MiB installer, over Wrangler's
  300 MiB upload cap), `npm run build`, then electron-builder **with the output outside the repo**
  (`npx electron-builder --win nsis --config.directories.output=<scratch dir>`; inside the workspace the
  `win-unpacked.tmp` rename fails with EPERM). Check it: `ACS_UNPACKED=<dir>/win-unpacked node
  scripts/smoke-packaged.mjs` (the first launch of a fresh unsigned exe can time out; rerun). Unsigned for now.
- **Upload:** `wrangler r2 object put ytclipper-releases/YT-Clipper-Setup.exe --remote --file <exe>` (private
  bucket, served by the Worker). Wrangler needs `NODE_OPTIONS=--use-system-ca` on this machine; run it from a temp
  dir, never inside the repo (it writes `.wrangler/` caches with account info; `.wrangler/` is gitignored anyway).
- **Site:** `cd apps/site && npm run build && vercel deploy --prod` (Vercel project `ytclipper`). The download button
  gates through Turnstile only when `VITE_TURNSTILE_SITEKEY` is set on Vercel; without it it falls back to the old
  public R2 link (see NEXT_STEPS).
- **Git:** the owner works on `quality-motion-openrouter` and has `main` fast-forwarded to it on request.
- Never read Wrangler/Vercel log files or credential stores; read only a command's own output (owner request).

## Owner decisions (2026-11-07, keep them)
- **Splash layout is approved as is: do not change it** (since 2026-11-08 at the owner's request: white theme, a tilted wall of the bundled renders drifting past,
  `components/TiltedTiles.tsx`, our own CSS take on React Bits Pro Tilted Tiles (no license), content on a solid
  white panel; staged word-by-word entrance,
  and since 2026-11-08 at the owner's request a React Bits BounceCards fan of five bundled design-engine renders
  in place of the aperture icon, `src/assets/splash/`).
- **White, flat, colourful contrast (owner pick 2026-11-08, after Lumin / Cloud Dock / Flix references; replaces the
  Galaxy Black / Seal Grey / Sunrise Orange palette):** cool off-white room `--color-ground` #f2f3f5, white panels
  (`.glass` is now a solid white panel), black `--color-ink` for text, the nav rail, primary buttons (`bg-pop` =
  black) and media frames, one vivid lime `--color-accent` #c6f432 used only as a solid fill (`chip-on` selection,
  the active rail item, `text-pop` = lime marker block behind one headline word); lime-coloured words use
  `text-accent-ink` #3d6b00. Create's three kind cards are full-bleed bundled photos (`src/assets/create/`, built
  once by `scripts/make-create-art.py` from Pexels, owner request 2026-11-08) with words on a solid white band.
  **No gradients anywhere** (no radial glows, no scrims: captions sit on solid bands). Fonts: Bricolage Grotesque
  headings (self-hosted from the backend's bundled OFL cuts, `src/assets/fonts/`) + Geist body.
- **App background = a dome gallery** (owner request + reference 2026-11-08): `components/DomeBackground.tsx`, the
  camera inside a sphere lined with rounded tiles of short looping clips (colour at 55%, `grayscale(0.45)`) (`src/assets/dome/`, animated WebP
  built by `apps/desktop/scripts/make-dome-clips.py` from free Pexels footage: every clip a different length, 3.2-5.4 s,
  with a crossfaded seamless loop, so tiles never visibly restart together), turning once every 3 minutes (CSS 3D,
  `dome-spin`, still under reduced motion), ghosted to 30% so page text reads on top. No WebGL: the silk wave
  (`Ember.tsx`) and cursor ink (`SplashCursor.tsx`) are no longer mounted (files kept, unimported). The splash is a tilted wall of renders
  (`TiltedTiles.tsx`) with its content on a solid white panel.
- **Library = React Bits Masonry** (`components/Masonry.tsx`, vendored, Phosphor icons, `renderAction` slot for
  delete + swatches): clicking a tile opens the full-screen carousel (arrows, Escape).
- **No full-size footage downloads before the user picks.** Generation proposes candidates (thumbnails only) with
  the AI's picks pre-selected; the user confirms on "Choose the footage"; the `visuals` job downloads exactly those.
- **One colour palette per project** (all pieces share it; later pieces inherit it).
- **Everything deletable individually:** assets, pieces, renders, clips, exports (refused while a job runs).
- Pages show real output only (rendered covers, clip frames, the piece's own quote on a lit frame), never stand-ins.

## Working rules
- **Ponytail:** laziest solution that works. Stdlib/native first, no one-implementation interfaces unless the PRD
  demands the abstraction (it does for CreativeModel, VisualProvider, TTSProvider, Renderer, Publisher). Mark
  deliberate corner-cutting with a `ponytail:` comment naming the ceiling. Never cut validation, security, data safety.
- **UI (taste + impeccable):** use the tokens and primitives; no one-off styles, no em dashes in UI copy, no eyebrow
  labels, no metric-card walls, no fake data or placeholder buttons for core features. Honest progress only.
- **Python is the source of truth** for pipeline logic; TypeScript never duplicates it. Renderer never sees API keys.
- **Rendering (M5):** ffmpeg always runs as a subprocess with argument arrays (never shell strings), wrapped with a
  timeout + kill so a hang can never wedge a job; always `-nostdin`/DEVNULL stdin and stderr to a temp file, never a
  stderr pipe. Windows drive-colon paths in drawtext need quoting AND escaping: `fontfile='C\:/...'`. Production
  renders default to 1080×1920; tests use small resolutions (540×960, ≤2s clips) per the user's ask — keep it that way.
- **Local and free (user decision, Milestone 7):** no accounts, no auth, no billing, no cloud storage — everything
  runs on this machine with local `media/` routes. Publishing integrations connect via API/MCP only (Buffer API,
  Metricool MCP) plus a CLI entry. Copying code from the user's ClipperAi repo is explicitly allowed.
- **Connecting a service is one button (owner, 2026-11-08):** Metricool uses OAuth 2.1 with dynamic client
  registration + PKCE through the shared loopback catcher in `publish/oauth.py` (no API key, no developer app).
  Publishing to Metricool goes through its MCP tools (`getBrandSettings`, `createScheduledPost`), one post per
  network with that network's copy. Users see plain-language errors only (`errors.explain`, download reasons in
  `clipper/acquire.friendly`); raw errors live under "View technical details".
- **Motion (motion-design skill, "Premium"):** `--ease-premium` in, `--ease-exit` out, exits shorter than entrances,
  never fade-only. Headings use `Reveal`; pages exit then enter via `App.go()`. A container holding `.glass` panels
  animates transform only (opacity/filter on an ancestor breaks backdrop-filter). Reduced motion turns it all off.
- **three.js:** no WebGL layer is mounted since the 2026-11-08 white redesign (`three` stays installed for
  `Ember.tsx` if it ever returns). If it does: plain `three`, a fresh canvas per mount.
- **Tests run motion off** (`ACS_NO_MOTION=1`), so any code path that only runs with animated titles needs its own
  test (the 2026-11-07 render crash hid there). In `render.py` never name a local `motion` (it is the module).
- **Smoke windows are real windows:** nobody may click them during a run; a click navigates away mid-job and fails
  the run. Ask the owner to leave them alone before running `npm test`.
- **Every phase ends with:** `npm test` from the repo root (backend unittest + typecheck + build + smoke), a look at
  the smoke screenshots, `graphify update .`, and an updated `NEXT_STEPS.md` (the current handover; `.claude/handover.md`
  is the M1-M8 log). Never claim something works without running it; say plainly what wasn't verified.
- Commit only when the user asks.
