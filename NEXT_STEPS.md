# Handover

Last updated 2026-11-08. This is the single source of truth for progress and next steps; `.claude/handover.md` is
the older milestone log (M1-M8) and is superseded where they disagree. Read this, then `.claude/CLAUDE.md`.

## Start here

- **Session 2026-11-12 (uncommitted): voiced quote videos rebuilt, music, voices, links.**
  - **Music:** the bundled library is now Lyria 3 Pro (OpenRouter, streamed audio) written to the owner's brief: slow felt
    piano, a little soft strings, a low cello/bass anchor, no drums/vocals (`scripts/make_music.py`, 12 x ~2 min,
    96k AAC, -20 LUFS). Old Commons tracks (Mountain King, Egmont...) removed. Owner should listen to `assets/music/`.
  - **Voices:** ElevenLabs eleven-v4 on the same OpenRouter key (`tts.NARRATORS` raspy=George, gravel=Clyde,
    deep=Brian, sage=Bill; PCM like Gemini). Genre defaults now raspy (stoic/history/books), gravel (speech), deep
    (cinema); hope keeps Gemini "warm". ~4 cents per voiced quote vs ~0.5 for Gemini.
  - **Voiced quote video** (`app/reveal.py`): "<Author> once wrote...", the quote, the book (`Quote.source`, new
    optional field the writer fills), then the lesson. Words appear 2-3 at a time centred (Instrument Serif), each
    finished section shows whole for 1.6 s (silence is inserted into the narration WAV where the voice ran on; the
    real speech end is found in the audio because STT stretches word ends), then the designed post cross-fades in for
    book + lesson. Brief `ken_burns` (default on: drift on the photo, push on the post) and `backdrop`
    photo|clips: clips = 5 Pexels videos per quote (quote searches + `assets.MOOD_CLIPS[genre]`), cut every ~2.5 s,
    dimmed in ffmpeg (`shot["dim"]`); the post is designed from the first clip's frame.
  - **Your own footage:** footage review has a per-piece links box: several Pexels photo/video or Unsplash photo
    links at once (commas, spaces or new lines; Ctrl+Enter adds), `visuals.add_links` -> `provider.by_id`, fetched
    concurrently. Yours play first in paste order; the piece grows to hold them all (`review.linked`, `base_want`,
    up to `MAX_SHOTS` 14; a plain picture post keeps 1); bad links are listed with a reason and left in the box.
    Each clip lends only a slice from its middle (`renders._behind_words`: ~2.5 s slots, down to `CLIP_MIN` 1.2 s
    so every pick is seen when the reveal is long enough). Live-checked Pexels lookup; the add flow is unit-tested.
  - **Unsplash fix:** `download_location` answers JSON `{url}`, not bytes; we stored the JSON as the photo. Fixed
    (ping, then fetch the url at w=1440, ixid kept). Only the Access Key is needed (Client-ID header); Secret Key
    and App ID are OAuth-only. Settings/Setup copy says so. Not live-tested: no Unsplash key on this machine.
  - Clip slots behind a voiced quote vary (owner): drawn from `renders.CLIP_RANGE` (2.0-3.8 s), seeded by the
    piece number so a re-render keeps its cut, scaled to fill the reveal (`renders._slots`).
  - **Checked 2026-11-12:** `npm test` passed in full (256 backend tests, typecheck, build, smoke; screenshots looked
    at, the links box renders under each piece). Real e2e renders at 540x960 (photo and clips), frames reviewed.
    **Installer 0.1.1 built** (`config.VERSION` and `apps/desktop/package.json` both bumped; 285,974,023 bytes,
    essentials ffmpeg, unsigned) to the session scratchpad `release/`; packaged smoke ok on the second run (first timed
    out as usual), reports 0.1.1. electron-builder needed `NODE_OPTIONS=--use-system-ca`. **Not uploaded to R2.**
    Not verified: the voiced-video toggles in a screenshot (smoke uses plain pictures), a full generate+render in the
    app with the new voices, music and clips.

- **Session 2026-11-10 (uncommitted): videos that tell real stories.** Owner: "Mansa Musa" gave a desert poem on
  four looping clips, ungraded, silent, in a soft robotic voice. Fixed:
  - **Documentaries:** `research.py` looks the topic up on Wikipedia (no key); the planner (`DOC_SYSTEM`) confirms
    it IS the subject (`BatchPlan.subject`, else a themed plan as before) and gives each piece its own facts
    (`PlanItem.facts`, none shared: 10 pieces = 10 chapters; the article grows with the batch, up to 24k chars).
    Narration states only sourced facts; the quote is optional (author null = the closing line, never fact-checked).
    Pieces keep `content.sources`, so regenerate stays factual. Live-tested on "Musa Mansa" (3 distinct chapters).
  - **No looping footage:** one shot per narration sentence (`assets.MAX_SHOTS` 14, `Visual.shots` up to 16);
    `edit.plan` uses each asset once unless the pool can't cover the voice at 1.8x cadence.
  - **Archival stills:** `CommonsProvider` (Public domain / CC0 only) for `role: "archival"` shots; landscape
    stills are shown whole over a blurred fill and pushed in (`renders._shots_for`, render.py blur branch).
  - **Matched grade:** `render.NORMALIZE` per shot, then stronger split-tone genre grades (`edit.LOOKS`).
  - **Music:** bundled public-domain/CC0 library `assets/music` (12 x 75 s, `scripts/make_music.py`, CREDITS.md),
    per genre, varied per piece (`music.py`), looped, ducked. Settings music file still wins; `bundled_music`
    setting (no UI toggle yet). FreePD is closed; Commons/Musopen used instead.
  - **Directed narrators:** `tts.NARRATORS` (persona + pacing note + the writer's per-piece `delivery` arc);
    "elder" = Algenib, wise grandfather (stoic/history/books default). Stoic used to default to Gacrux (female).
  - **Quote images** = the quote (now up to ~60 words, `Quote.text` 420 chars) + author, nothing else; long quotes
    skip Polaroid (`design.SHORT_ONLY`). **Voiced quote video** reads quote, author, then `lesson`: 2-4 sentences
    on THAT quote (`prompts.LESSON`, only for `image_voiced`).
  - **Clips:** floor back to **60 s** (`config.MIN_CLIP`, brief + Create form defaults 60/120); a pick that can't
    grow earlier now runs on past its end until the minute is met (`clips._at_least`). Count uncapped: one per
    2.5 min of speech (`clips.PER_CLIP`), limited only by what fits (an hour ~ 24); brief `n` up to 200.
    **Every clip gets a quiet bundled bed** (`music.for_clip`, calm moods only, ~22 dB under speech, gently ducked).
  - Music build hit Wikimedia's 429 rate limit; `make_music.py` now resumes, paces 15 s, uses cached .ogg originals.
  Checked: 245 backend tests, typecheck, a small mixed-shot render with music, 13 designs with a 58-word quote.
  **2026-11-11:** `npm test` passed in full (smoke included); installer built (268 MiB, 0.1.0, unsigned) to the
  session scratchpad, packaged smoke ok (second run; the first timed out as usual). **Not uploaded to R2.**
  Clip mix measured on a real clip render: speech -15.8 LUFS, bed -48 LUFS under speech (ducked ~13 dB, so ~32 dB
  below the voice) and -35 LUFS in pauses. It can't mask speech; it may be too faint (raise `music.CLIP_VOLUME`). **Not run:** `npm test` smoke, a full
  generate+render in the app, an installer build (music adds ~12 MB).

- **Session 2026-11-08 evening (uncommitted, installer uploaded 2026-11-09):** author line on the statement and stack
  designs; detailed job progress (step log per job, migration 013, ffmpeg progress, per-piece failures logged and
  shown on the piece, `components/JobProgress.tsx`); a lime halo on every selected option (`.halo`, `.halo-sm`);
  CSV sample + AI prompt buttons on "I have my own"; **every quote is a real documented public-domain line with its
  author, in every genre** (owner pick; `prompts.ATTRIBUTION`, `content._signed` retries unsigned quotes); pasted CSV
  rows split into quote + author; **clips run at least 60 s finished** (`clips.MIN_CLIP` / `ACS_MIN_CLIP`, grown
  after tightening by `clips._at_least`); **no approve step** (migration 014 turns approved into ready;
  `pieces.approve` removed) and **Schedule all** for clips and pieces (`posts.schedule`, `ScheduleAllDialog`: first
  post + every 10 min / 15 min / hour / day / other day, each time editable). The posting calendar is gone.
  Checked: 224 backend tests, typecheck, build, packaged smoke. **Not run: `npm test`'s smoke** (updated for all of
  the above). Not tried for real: a generation with the real-quote prompts, Schedule all against Zernio.
- **Committed and pushed 2026-11-09 as `e3b2311`** (everything below). **Installer rebuilt and uploaded 2026-11-09 05:10**
  (includes the creator card) to both R2 copies; verified public link 200 at 268,732,600 bytes, gate 400 without a
  token. `apps/desktop/release/` now holds only that one installer (owner: one, not several).
- **Site deployed 2026-11-09:** posting copy now says Zernio (home, terms, privacy table); `robots.txt` +
  `sitemap.xml`; IndexNow key `ed4c4a3fb4f795112f68126f75b83204` (file at the site root). All five pages submitted to
  IndexNow (202 accepted); resubmit after site changes with the same POST to api.indexnow.org. Google Analytics was
  built (consent banner) then dropped at the owner's request: no analytics, privacy page says so. Search Console not set
  up yet (needs the owner's verification code; the sitemap is ready for it).
- **Creator card (2026-11-09):** React Bits Lanyard
  (`components/Lanyard.tsx`, vendored, `@ts-nocheck`) in `components/CreatorCard.tsx`, mounted in the Shell. Drops in
  1.2 s after a `render`, `visuals_render` or `clip` job completes, at most twice a day (localStorage
  `acs.creatorCard`); Escape, backdrop or Close dismiss it; under it three icon links (website, LinkedIn, GitHub) and Close. After each drop
  it settles on the front, flips to the back ~5 s in, rests 2 s and turns home (Lanyard `peek` prop, ours). Card art
  (front with the owner's portrait `scripts/creator-photo.png`, back, strap) drawn by
  `scripts/make-creator-card.py` into `src/assets/lanyard/`. three.js loads lazily (1.2 MB chunk) only when it opens.
  Verified in the built app by screenshot (drop-in, flip, Escape). The smoke run disables the daily pop-up and opens
  it once via the `creator-card:open` window event.
- **Installer 2026-11-09** (all of the above, still 0.1.0, unsigned, 256 MiB) replaced BOTH R2 copies:
  `ytclipper-releases/YT-Clipper-Setup.exe` (gated) and the public `clipperai-published/downloads/YT-Clipper-Setup.exe`
  (what the site button serves until Turnstile is live). Verified: public link 200 with the new size; gate 400
  without a token. Local copy in `apps/desktop/release/` (older builds in `previous-*`).

- **Shipped 2026-11-08.** `main` = `quality-motion-openrouter` = `cde8ffe` on GitHub (release 0.1.0).
- **Committed 2026-11-08 on `quality-motion-openrouter` (not yet on `main`):** Zernio-only posting (Buffer and
  Metricool removed) for clips, quote images and narrated videos; "Download and render"; six new image designs (13
  total); the post-dialog overflow fix and confirmation; simpler quote content (no emphasis, no kicker); batch writing
  (one AI request per group of pieces); quote images skip planning; the redesigned landing site (deployed) plus three
  copy fixes (not deployed). Checked: 221 backend tests, typecheck, desktop build. **Not run: `npm test`'s smoke
  step** (updated for every change; it opens real windows, so ask the owner to keep hands off first). Next: smoke,
  then fast-forward `main` if the owner asks, rebuild the installer, deploy the site copy fixes.
- **Live:** site https://ytclipper.xyz (Vercel project `ytclipper`, root `apps/site`); installer 0.1.0 (256 MiB,
  essentials FFmpeg, unsigned) in the private R2 bucket `ytclipper-releases`, served by the Worker
  `https://ytclipper-download.jafaruhasbiyallahu-cc1.workers.dev/download` after a Turnstile check; a public copy
  still sits in `clipperai-published/downloads/YT-Clipper-Setup.exe` until the gate goes live (below).
- How to build, upload and deploy: `.claude/CLAUDE.md` "Release and deploy". Binding owner decisions: its "Owner
  decisions".
- Repo `.env` (gitignored) holds real `OPENROUTER_API_KEY` and `PEXELS_API_KEY`. Never print them.

### Waiting on the owner
1. **Turnstile:** create the widget (Cloudflare, Turnstile, Add widget, hostnames `ytclipper.xyz` +
   `www.ytclipper.xyz`, Managed), run `npx wrangler secret put TURNSTILE_SECRET` in `apps/download-worker`, and send
   the site key. Then: `vercel env add VITE_TURNSTILE_SITEKEY production` (site key), redeploy the site, test a real
   download end to end, then **delete** `clipperai-published/downloads/YT-Clipper-Setup.exe` (the bypass).
2. **DNS to Cloudflare:** add `ytclipper.xyz` as a Cloudflare zone (A `@` 76.76.21.21 and CNAME `www`
   cname.vercel-dns.com, both DNS only), switch the nameservers in Vercel's domain settings. Then attach
   `download.ytclipper.xyz` to the Worker (or bucket) and point the site's `GATE` at it. Registrar transfer to
   Cloudflare possible from about 2026-11-14 (60-day lock).
3. **Zernio, the rest of the real checks:** TikTok with a quote image is verified (below). Still to try for real:
   a narrated video to YouTube (becomes a Short), a clip, a scheduled (not "now") post, unscheduling one, and the
   Plan calendar. The owner's key is in the dev data; accounts connected: YouTube "The Micro-Fix", TikTok
   "Jafar </> Builds Web Apps".
4. **Legal pages:** confirm governing law (set to Nigeria, inferred from the time zone, not confirmed) and the
   contact route (points to hasbiyallahu.xyz). Plain-language drafts; a lawyer should review before commercial use.
5. **Code signing:** the installer is unsigned, so SmartScreen warns on first run (the site FAQ explains it).

### Still unverified with real accounts
- **Zernio:** verified live 2026-11-08: key save, account list, connect links, and one quote image posted to TikTok
  (published 34 s after its slot). Not yet live-tested: YouTube, clips, scheduling ahead, unscheduling, calendar.
  TikTok returned no public post link for the photo post, so its chip says Posted without a link.
- A real clip of a real video end to end in the packaged app, and a real render by eye and ear (old step 12).

## Installer 2026-11-09 (evening): built, not uploaded
All audit phases + voiced quotes (`image_voiced`). Backend 240/240, `npm test` smoke OK, packaged smoke OK (2nd try),
268.7 MB. electron-builder needs `NODE_OPTIONS=--use-system-ca` here too (its NSIS download fails TLS without it).
Real run: 9.8 s narrated video verified (sync, BT.709, 0 misstamped packets); the YouTube test post was refused by
YouTube's daily upload limit (uploadLimitExceeded), so on-platform playback is still unchecked. Not uploaded to R2.

## Full system audit (2026-11-09): work from `AUDIT.md`
Every finding from the five-area audit is a checkbox in `AUDIT.md` (repo root), grouped into fix phases 1-6. Tick
items there as they're fixed, with the date and how it was verified. Phase 5 (virality) needs owner sign-off.

## Posted videos warped for their first seconds (fixed 2026-11-09, uncommitted)
- Cause: `loudnorm` (clips in `clipper/render_clip.py`, narration in `render.py`) stamped the opening AAC packets
  1 sample apart for ~0.64 s, then jumped to 3.0 s. Local players ignore it; platform transcoders obey the stamps,
  so the start sped up / dragged after posting through Zernio. Every existing clip has it (118 bad packets each).
- Fix: `loudnorm=...,aresample=48000,asetpts=N/SR/TB`. Guard: `render.audio_misstamped` fails any render whose
  AAC packets aren't all 1024 samples (`validate_video` + after each clip render). Backend tests 225/225 OK; real
  14 s two-range clip renders clean. Not yet verified: an actual post of a new render. Old renders must be
  re-rendered (or audio re-encoded with the same filter, `-c:v copy`) before posting.

## Zernio posting, new designs, landing site redesign (2026-11-08, uncommitted)

- **Posting through Zernio** (owner pick, the recommended way): `app/publish/zernio.py`. Settings has a new visible
  **Posting** section with three numbered steps (make a free account, copy an API key, paste it), then the connected
  social accounts and one button per network to add another (browser sign-in through Zernio). Zernio hosts the
  video itself, so no media host is needed.
- **Buffer and Metricool are removed completely** (owner, same day): `buffer.py`, `metricool.py`, `oauth.py`,
  `host.py` and `tests/test_publish.py` deleted; shared publications logic moved to `app/publish/posts.py`; settings
  fields and the Advanced panel gone; first-run Setup's Metricool step is now "Post to your socials" (Zernio);
  CLI has `accounts` and `publish --accounts`; migration 011 deletes their saved connections.
- **Publish dialog** is Zernio only; before Zernio is set up it offers "Open Settings". TikTok picks show
  TikTok's Music Usage Confirmation line (TikTok requires it).
- **Calendar** schedules through Zernio (`posts.calendar`, RPC `publish.calendar`).
- **Quote images and narrated videos can be posted too** (`zernio.publish_piece`, RPC `publish.zernio_publish_piece`):
  a Post button on every rendered piece opens the shared `PostDialog` (components/Posting.tsx). The video goes when
  the piece has one, else the image (YouTube is disabled for images: videos only). Each network's text comes from the
  piece metadata with the export's hashtag rules (`zernio.piece_texts`). Migration 012 adds `publications.piece_id`.
- **First real post (2026-11-08):** a quote image to TikTok went out through Zernio at 17:15:51, 34 s after its slot.
  Found and fixed: TikTok's creator-info returns privacy levels as `{value, label}` objects (Zernio accepted the
  object anyway); the post dialog spilled past its panel on long titles (Dialog grid now `minmax(0,1fr)`, every
  dialog); the dialog now shows a "Sent to Zernio" confirmation per account instead of closing silently.
  Zernio pricing (zernio.com/pricing): first 2 accounts free, unlimited posts; no documented schedule horizon.
- **Simpler quote content:** the AI no longer writes an "emphasis" phrase or a "kicker" line; a quote is its text
  and author only (`Quote` schema, `QUOTE_FIELD`, `design.copy_for`). Old pieces that still carry them load fine.
  Clip subtitles keep their own key-word colouring (a different feature).
- **Quote images simplified:** no planning call any more (`content.quote_plan` is a fixed stand-in, no AI) and no
  design hints in their JSON (`PieceContent.design` is optional; narrated videos still require it). Flow for quote
  images: write in groups of 8 -> footage options -> Download and render -> render -> post. 20 quote images = 3 AI
  calls. The progress line reads "Writing quotes 1-8 of 20". Narrated videos keep their planning step for now.
- **Batch writing:** pieces are written in groups, one AI request per group (8 quote pieces or 4 narrated pieces;
  `content.WRITE_GROUP_*`, `prompts.pieces`, `OpenRouterModel.write_pieces`). A malformed or repeated piece falls back
  to the single-piece call; three tries per piece in all, the batch draft included. Own CSV quotes batch too.
  Regenerating one piece still uses one call.
- **Six new image designs** (`design.py`, researched against 2026 feeds): Notes page, Book highlight, Riso print,
  Film subtitle, Instant print, Swiss grid. 13 designs total; every genre now rotates through 5-6.
- **"Download and render"** (was "Download N shots and continue"): the button now sits under the footage shots and
  starts the new `visuals_render` job, which downloads the picks and then renders every piece on one progress bar;
  the page scrolls to the progress bar. The smoke's fake Pexels now serves a real 14 s clip so no swap step is needed.
- **Every clip now shows where it is going:** status chips (Scheduled / Posting now / Posted / Failed, with the
  network and time); a posted chip opens the live post, the x unschedules. Zernio statuses refresh every
  minute while anything is pending. Cancelled posts no longer block rescheduling.
- Tests: `tests/test_zernio.py` (fake REST API + fake presigned storage), 220 backend tests green, typecheck and
  build green. **The smoke run was not done** (it needs the owner to keep hands off the windows) and the new
  Settings section has not been seen in a screenshot yet.
- **Site:** redesigned `apps/site` (endless three.js production-line hero, pinned "cut" scroll scene, GSAP +
  Lenis, light only) is live on ytclipper.xyz; three copy fixes after that are local only, not deployed.

## Release + publishing (2026-11-08)

- **Download:** the installer lives in the private bucket `ytclipper-releases` (`YT-Clipper-Setup.exe`) and is
  served only by the Worker in `apps/download-worker` after it verifies a Turnstile token (single use, 5 minutes,
  issued on ytclipper.xyz). Verified: no token 400, fake token 403. The site gates the button once
  `VITE_TURNSTILE_SITEKEY` is set; until then it uses the old public copy in `clipperai-published` (delete that
  copy once the gate is live). 300 MiB Wrangler cap, so package with the essentials FFmpeg.
- **Legal pages:** privacy, terms, license (EULA), open-source on the site, generated by
  `apps/site/scripts/make-legal.py` (edit there, rerun from `apps/site`).
- **Site:** live at https://ytclipper.xyz (Vercel project `ytclipper`, root `apps/site`, `vercel deploy --prod`).
- **Metricool publishing:** `metricool.brands()` / `metricool.publish()` via the MCP tools getBrandSettings and
  createScheduledPost (one post per network with its own copy, video via the media host, planner link stored).
  Brand reply shape only seen in its no-networks error; verify with a connected network. No delete tool, so a
  scheduled Metricool post is removed in Metricool's planner.
- **Clip preview redesign:** video fits the panel (grid row + flex fix, also in the piece preview); post copy has
  network tabs, character limits, Copy, hashtag chips; Publish dialog picks Buffer or Metricool.

## Landing site ytclipper.xyz (2026-11-08)

- `apps/site/`: Vite + plain TS + three.js, one page, for download. `npm run dev|build|preview` inside it. Hero is
  `src/hero.ts` (real renders as a film strip, a lime playhead cuts it, pieces lift into a fan; auto-fits by
  projecting the loop's poses; pauses off-screen; still under reduced motion). Images come from the app via
  `scripts/prepare-assets.py` (renders, real UI screenshots, icon, og.png). Light + dark.
- Vercel: project root `apps/site` (vercel.json there). Domain ytclipper.xyz still to attach.
- **Download link** (`src/main.ts` DOWNLOAD_URL) expects a GitHub release asset named `YT-Clipper-Setup.exe` on
  HasbiyallahuJafaru/aicontentstudio; no release exists yet, so the button 404s until one is published.

## One-click Metricool + first-run setup screens (2026-11-08, uncommitted)

- **Clip from your own file:** the Video field has **Choose a file** (native picker, `app:pickVideo` IPC) and takes a
  dropped video (`studio.pathForFile`, Electron webUtils). The backend already clipped local paths as-is.
- **Plain-language errors everywhere:** `errors.explain(e)` turns unplanned exceptions (no internet, full disk, locked
  file, out of memory) into calm words for every RPC and job; `acquire.friendly()` now names rate limits (429), IP
  blocks (403), bot checks, age/private/members-only/region/removed videos, live streams, bad links and no internet,
  with a calm fallback. Raw errors stay under "View technical details". `tests/test_errors.py`.
- **Create cards:** one bundled photo per kind (`src/assets/create/`, credits JSON), no runtime fetching.
- **Dashboard crowd:** cards spaced by their real widths, no overlap.

- **Metricool connects with a button** (`publish/metricool.py`): Metricool's auth server allows dynamic client
  registration + public PKCE clients, so the app registers itself once (`metricool_client` in the credentials
  table), opens the consent page, and the shared loopback catcher (`oauth.py`, now provider-agnostic via
  `oauth.begin(provider)` + `EXCHANGES`) stores the bearer token. The `METRICOOL_API_KEY` secret is gone.
  RPC: `publish.metricool_connection|connect_url|disconnect`. Verified against fakes only.
- **Setup screens** (`pages/Setup.tsx`): after the splash, if the OpenRouter or Pexels key is missing, one screen
  per key (OpenRouter, Pexels, Unsplash optional), Connect Metricool, then a summary; every step skippable.
  Smoke walks it on its fresh first launch (`0c/0d/0e-setup-*.png`); smoke:packaged skips through it.
- **Installer built 2026-11-08** (`apps/desktop/release/AI Social Content Studio Setup 0.1.0.exe`, 331 MB, unsigned).
  Build gotcha: electron-builder's rename `win-unpacked.tmp -> win-unpacked` hit EPERM every time inside the
  workspace (something, likely VS Code's watcher, holds the fresh folder). Building outside the repo works:
  `npx electron-builder --win nsis --config.directories.output=<folder outside the repo>`, then
  `ACS_UNPACKED=<that>/win-unpacked node scripts/smoke-packaged.mjs`. The first packaged launch can time out
  (unsigned exe being scanned); the second run passed.

## White redesign + Library carousel + rail label fix (2026-11-08, uncommitted)

Owner: the inside of the app lacked imagery and the colours were off; wants a white background, a colourful
contrast palette, no gradients, a more artistic font pairing (references: Lumin, Cloud Dock, Flix). Taste skill used.

| Change | Where |
|---|---|
| Tokens: white flat room, black ink/rail/primary, lime accent as solid fills only, content tiles (lime/violet/coral/sky), `text-accent-ink` for lime words. `.glass` = solid white panel; `.ambient` flat; grain, glows, spotlight glow, button sheen removed. | `styles/index.css` |
| Fonts: Bricolage Grotesque headings (self-hosted from `apps/backend/assets/fonts`; the npm install hung on this network) + Geist body; Sora no longer imported (package still installed). | `styles/index.css`, `src/assets/fonts/` |
| Every gradient removed (Cover, Create, Dashboard, Library, Splash); dark-theme tints swept to light; Create kind cards on solid lime/violet/coral tiles. | sweep over `components/*`, `pages/*` |
| Shell: black rail, lime active item, black tooltips, no canvases (Ember + SplashCursor unmounted, files kept). Splash: colourful tilted wall, content on a white panel. | `layouts/Shell.tsx`, `pages/Splash.tsx` |
| **Rail labels drew under the page** (owner report): the rail's entrance animation keeps a transform, which gives it its own layer below the page's. Fix: `relative z-20` on the rail. Smoke checks it with motion on (proved: fails without the fix, passes with it). | `Shell.tsx`, `scripts/smoke.mjs` |
| **Library = React Bits Masonry** with full-screen carousel (arrows, Escape, open/close animations); vendored with Phosphor icons (no @hugeicons), a `renderAction` slot (delete on hover + colour swatches), solid caption band, white lightbox; drag-to-reorder off (order isn't stored). Smoke opens it, steps, closes. | `components/Masonry.tsx/.css`, `pages/Library.tsx` |

| **Dome in colour**: the clips keep 55% of their colour (`grayscale(0.45)`, owner request), still shown at 30% so text reads on top. Alternative reading if the owner meant overall strength: set the tile opacity instead. | `index.css` `.dome-tile img` |
| **Dome plays clips** (owner: posters looked repetitive, wants the feel of video, lightweight; then: all tiles restarted at the same moment): 12 free Pexels clips as seamless animated WebP loops, each a different length (3.2-5.4 s, the last 0.6 s crossfades into the start, so no clip ever snaps back), ~2.4 MB total; frame counts and seam smoothness checked per clip, a near-black candle clip and a frozen rain clip were replaced. | `scripts/make-dome-clips.py`, `src/assets/dome/`, `Shell.tsx`, `DECISIONS.md` |
| **Background dome** (owner: "a rotating image gallery as the background", reference image of a dome gallery): the camera inside a sphere lined with rounded greyscale tiles (28 columns x 9 rows of the bundled renders), turning every 3 min, ghosted to 22% behind the pages; the title bar is a solid strip over it. CSS 3D only. (A Library "Orb view" was built first and removed: the owner wanted the background, not a Library feature.) | `components/DomeBackground.tsx`, `index.css` `.dome-*`, `Shell.tsx` |

Verified: typecheck, build, smoke (several runs), screenshots reviewed (splash, dashboard, create, quote images,
exports, library, carousel, settings). Not run since: backend tests (no backend change in this pass). Not seen: the
splash drift and Masonry entrance with motion on (smoke runs motion off).

## Splash background: tilted wall of renders (2026-11-08, uncommitted)

Owner asked for React Bits Pro "Tilted Tiles" behind the splash. Pro needs a paid license key (none on this machine,
no shadcn setup), so `components/TiltedTiles.tsx` is our own CSS version: 11 tilted columns of the 8 bundled
design renders (`assets/splash/`), each column doubled and sliding half its height (seamless), alternate columns
reversed at 48/62/76 s; `tile-up` keyframes under no-preference in `index.css` (reduced motion: still wall). It
replaces the Ember glow on the splash only (Ember no longer loads there); 35% opacity under a Galaxy Black radial so
the fan, title and button read. Verified: typecheck, build, smoke, splash screenshot reviewed (a still frame:
smoke runs motion off, so the drift itself was not seen).

## ClipperAi port: what was missing around the engine (2026-11-08, uncommitted)

Owner asked to review the ClipperAi repo (GitHub HasbiyallahuJafaru/ClipperAi, main) and bring over anything missing.
Finding: the engine (`clipper.py`: acquire, Whisper chunks, two-pass selection, snap, face crop, captions, render)
is fully in `app/clipper/` already, and ours is ahead (glides, tightening, cold open, styled captions, motion
titles). Billing, accounts, cloud storage, mobile and website stay out (local and free). Owner picked all five extras:

| Feature | Where |
|---|---|
| **Edit clip copy**: title, hook, description, hashtags, each platform's post; a post over its network limit is refused with the numbers, never trimmed (ClipperAi ClipEdit). "Edit copy" in the clip preview. | `clips.update` (`clips.py`), `Clips.tsx CopyEditor` |
| **Export spreadsheet**: a clip export also writes `<project>_clips.csv` (BOM, one column per platform) and `<project>_clips.json`; deleting the export removes them. | `export._clip_sheets` |
| **Name + thumbnail before download**: public oEmbed (YouTube, Dailymotion, TikTok, X, Vimeo, ...) names the project and stores its thumbnail (`brief.thumb`, `media/clipwork/thumbs/`) in a background thread right after create; never overrides a name set meanwhile; the thumbnail is the project cover until clips exist and shows in the clip header. | `app/clipper/preview.py`, `projects.py` |
| **Plain downloader**: "Just download the video" under the link on the clip form; MP4 to ~/Downloads with progress and "Show in folder" (Explorer, only paths it wrote). Shares yt-dlp options and bot-check wording with clipping (`acquire.options` / `friendly`). | `app/downloader.py`, `Create.tsx DownloadOnly` |
| **Posting calendar**: the backend already had `publish.buffer_calendar`; added `dry_run` (ClipperAi's plan step) and the UI: "Plan calendar" on a clip project with approved clips, channels, weekdays, times, start date, a preview of every slot, then "Schedule N". Channel picker shared with single-clip publish. | `publish/buffer.py`, `Clips.tsx CalendarDialog` |

Verified: 12 new backend tests (`tests/test_clipper_extras.py`, no network) and the other backend tests except one,
typecheck, build, smoke (screenshots: clip form, clip project, preview with "Edit copy"). One failure:
`test_motion` real render, Edge exits on launch ("Target closed", 69 Edge processes running): machine state, the same
test passed earlier today and motion.py is untouched. **Not verified by eye or test:** saving an edit in the UI,
the calendar dialog against real Buffer, a real YouTube download through the button, a real oEmbed fetch.

## 60-30-10 palette 2: Galaxy Black, Seal Grey, Sunrise Orange (2026-11-08, uncommitted)

Owner asked to try a second palette, same rule, same layouts. Replaces the white/black/red pass below (its notes stay
for the history). Galaxy Black #111216 ground, Seal Grey #4a4c50 glass/rail/inputs, Sunrise Orange #e67451 accent
(only Sunrise Orange has a published hex; the other two are our picks, swap in `styles/index.css` if the owner has
exact values). Text on orange is Galaxy Black (`--color-on-accent`) because white on #e67451 fails AA. `chip-on` is an
orange tint with orange text. Silk/glows/embers repainted (`Ember.tsx`), cursor ink orange + grey (`Shell.tsx`),
component tints swept back to the dark-theme versions. Verified: typecheck, build, smoke (first run failed, cause
not captured; the rerun passed), screenshots reviewed (splash, dashboard, quote images, project).

## 60-30-10 recolour: white, black, hot red (2026-11-08, uncommitted)

Owner: "the colours do not match, I don't like the purple gradients"; wants white 60 / black 30 / hot red 10, same
structure and layouts. Colour-only change; Ember Pop below is superseded.

| Change | Where |
|---|---|
| Tokens flipped to light: ground #f5f5f3, panel white, ink #0c0c0e / #45454b / #6e6e75, black hairlines, accent and `--color-pop` hot red #e5102e (white text passes AA), danger #b4161b, ok #23803a; `--color-violet` removed. `bg-pop` solid red, `chip-on` solid black, `text-pop` solid red, white glass, faint red spotlight and ambient. | `styles/index.css` |
| Silk + glows repainted (white cloth, graphite folds, red rim mixed not added, red embers with normal blending); `pop` prop deleted, splash and Shell share one palette. | `components/Ember.tsx` |
| Background silk now flows all the time (owner request), not only during jobs; embers still mark a running job. | `layouts/Shell.tsx` |
| Black nav rail with red active item; tooltips black with white text; cursor ink red + black; dark tints swept to light ones; inputs, dropdowns and the modal white; video/media frames and placeholder covers black; text on photos white. | `layouts/Shell.tsx`, `components/*`, `pages/*` |

Verified: 204 backend tests, typecheck, build, smoke (first run failed on a stray click navigating to the Dashboard
mid clip job, the rerun passed), screenshots reviewed (splash, dashboard, create, quote images, project, preview,
queue, library, exports, settings, footage review). **Not checked by eye:** the clips page beyond the smoke run.

## Ember Pop redesign, subtitles default, dashboard drafts (2026-11-08, uncommitted)

Owner feedback: "monochromatic, doesn't appeal to the younger generation"; owner picked **Ember Pop** (keep the dark
warm base and ember orange, add coral pink + electric violet). Redesign skill audit applied.

| Change | Where |
|---|---|
| Tokens `--color-pop` / `--color-violet`; utilities `bg-pop` (contrast-safe gradient), `chip-on` (the one selected look), `text-pop` (gradient keyword, drifts with motion on), `btn-shine` (hover sheen), `spotlight` + `spot()` (cursor light on cards). `.ambient` gains coral + violet lights. | `styles/index.css`, `components/ui.tsx` |
| Primary buttons gradient + sheen; every selected chip / Queue tab / Library filter / palette chip uses `chip-on`; swatch selection ring in coral; active rail item tinted; step bar + all progress bars gradient; FootageReview pick numbers gradient. | `ui.tsx`, `StylePicker.tsx`, `Queue.tsx`, `Shell.tsx`, `Create.tsx`, `Project.tsx`, `Clips.tsx`, `FootageReview.tsx` |
| Silk wave `pop` mode: rim light violet (left) -> coral -> ember (right, under the lamp), plum deep folds; glow layer adds coral and violet lights; a screen-blend colour wash over it. Splash keeps the original (`pop` off). Pointer ink: orange, coral, violet. | `components/Ember.tsx`, `layouts/Shell.tsx` |
| Dashboard: headline keyword "making" in gradient; hero and choice cards spotlight; crowd shows the newest PIECES (`pieces.showcase`): rendered image, or a labelled "Draft" frame of the quote, so generated content appears at once and a deleted render shows as a draft, never a finished post; reloads when a job finishes (`useBusy`). | `Dashboard.tsx`, `content.showcase`, `rpc.py` |
| **Subtitles default ON** for narrated videos (backend default and Create), with the reason shown. Investigation: subtitles were proven to burn across every shot (multi-shot render with real motion layers, frame diffs at every 0.5 s, and real Whisper timings across a 17.8 s narration); the "only on the first clip" text was the hook title (first 2.6 s) on a render with subtitles off. Footage is already trimmed per shot (each shot takes ~1.5-3 s from its own seek point). | `projects.py`, `Create.tsx` |

Verified: 204 backend tests, typecheck, build, smoke, screenshots reviewed (dashboard, create, quote images, settings,
queue, library, exports). Smoke run once flaked (Export button detached during an owner message mid-run); the rerun
passed with no console errors.

## Generation engine overhaul + stock budget + palette (2026-11-08, uncommitted)

Owner report: every request came back as an early-morning narration script ("At 5:47 a.m. you step outside...
The breath you see is proof you stayed"), off the topic, and as a script even for quote images. Causes: the one
system prompt modelled "The alarm reads 4:52" and asked twice for "an hour of the day"; the planner asked for "a
4am-style moment"; one recipe served every kind of content; nothing pinned down what the topic meant.

| Change | Where |
|---|---|
| **Two writers.** QUOTES_SYSTEM (quote images: quotes only, 4-22 words, facets of the topic, one photo search) and VIDEO_SYSTEM (narrated shorts, the craft kept, shots kept). Shared TOPIC_RULES: read the topic literally, never drift to a neighbouring theme, images from the topic's own world, timestamps/alarms/"you step outside"/gyms/mirrors banned unless asked. Genre voices split into `quote` and `voice`; "2am" and the 4:52 examples gone. | `creative/prompts.py` |
| **Topic reading.** The plan returns `reading` (one sentence of what the user means); stored on every piece (`content.reading`) and fed to every piece prompt and to "redo one part". Each piece prompt ends with a drift self-check. | `schemas.BatchPlan.reading`, `content.py` |
| Quote pieces carry no narration (`PieceContent.narration` optional; `VideoPieceContent` requires it for anything that may become video). UI hides narration and its "Redo" for them. | `schemas.py`, `model.py`, `Project.tsx`, `Preview.tsx` |
| **Stock budget.** Providers in order (Pexels first; Unsplash only if fewer than 3 usable results), one request each; 6-hour search cache (re-rolls cost nothing); lazy queries (an image piece normally costs ONE search, a video piece one per shot, flat fallback queries only if needed); progress shows "N stock searches so far". Was: up to 6 queries x every provider per piece. | `assets/__init__.py _search_all, _propose_one` |
| **Footage colour.** `brief.palette` (auto, warm, cool, earth, mono, dark, light): photos filtered at the source (Pexels `color`, Unsplash `color`), every candidate (videos too) ranked by thumbnail match; auto = no filter, soft lean to the genre's look. Picker on the quote-images Design step and the videos Look step. | `visual.PALETTES/palette_match`, `providers.py`, `StylePicker.tsx PalettePicker` |
| Bugs: a quote piece without narration crashed the project page into a blank window (fixed, plus a `PageBoundary` so no page can blank again); the Dashboard crowd showed quote frames for pieces whose render was deleted (now real renders only). Dashboard crowd sized from the room under the buttons (cqh), smoke asserts no overlap at 1024/1440/1920. | `Project.tsx`, `components/PageBoundary.tsx`, `Dashboard.tsx` |

Verified on the owner's real data: a fresh "beauty of autumn" generation came back on topic with a reading and no
narration. **Not verified:** a video generation with the new writer through OpenRouter; real Pexels palette results.

## Dashboard hero (2026-11-08, uncommitted)

Owner reference: a centred landing hero (two-line headline, one sentence, dark + light pill buttons, a crowd of
people rising from the card's bottom edge); our colours, no nav bar. Built as one glass card:

| Change | Where |
|---|---|
| Headline "Good morning, / what are we making today?" (Reveal), the real activity sentence, "New project" pill and a "Pick up {latest}" pill with the project's real cover as its avatar. | `pages/Dashboard.tsx Hero` |
| The crowd: seven tiles in an arch rising from the card's bottom edge (newest work biggest, front and centre; tilts lean inward; a soft floor fade). Real covers first (clickable, open the project), written-but-unrendered pieces on their lit frames next, then bundled design-engine samples (8 in `src/assets/splash/`, never repeated, not clickable). Splash keeps the first five. | `Dashboard.tsx SLOTS/PROMINENCE` |
| Recent projects grid stays below; first run shows three steps under the hero. The old "Pick up where you left off" card (with progress bars) is gone; the grid shows each project's state. | `Dashboard.tsx` |

Verified: typecheck, build, smoke (dashboard empty and with data, `6b-dashboard-data.png`), screenshots reviewed.

## Bulk CSV quotes, pointer ink, splash card fan (2026-11-08, uncommitted)

| Change | Where |
|---|---|
| **CSV import** for "I have my own" quotes: button or drop onto the box. Python parses it (`quotes.from_csv`): delimiter sniffed (comma, semicolon, tab, pipe), UTF-8 / UTF-16 / Excel cp1252, header names recognised (quote/text/line + author/by/source, any order), no header = quote + author only when the second column reads like names (else each row is one quote that contained a comma). Every skipped row comes back with its reason (too long, too short, repeat, past the limit). Lines land in the box as editable "quote — Author". | `app/quotes_csv.py`, `Create.tsx QuotesInput`, `tests/test_quotes_csv.py` |
| **Bulk:** own quotes up to 100 per project (AI-written stays 20); planning runs 20 at a time. `split_author` no longer treats a plain hyphen as an author unless what follows reads like a name ("Work hard - play hard" stays whole). | `projects.py`, `content.py` |
| **Pointer ink** (owner request): React Bits SplashCursor in the Shell's background layer, ember palette, medium quality, behind the glass, no intro, off under reduced motion (`useReducedMotion`, live). | `components/SplashCursor.tsx`, `layouts/Shell.tsx`, `lib/studio.ts` |
| **Splash card fan** (owner request, unlocks the splash for this): React Bits BounceCards in place of the aperture icon, five bundled square renders from our design engine (noir, paper, statement, classic, stack). | `components/BounceCards.tsx`, `pages/Splash.tsx`, `src/assets/splash/` |

Smoke covers: CSV import (2 added, 1 skipped with reason), the splash fan (5 decoded images), pointer ink absent
under reduced motion and drawn with motion on (`0b-pointer-ink.png`).
**Not verified:** the ink's look and cost on the owner's 1.5x display while a job animates the silk (two WebGL
layers at once); regenerate `src/assets/splash/` with the design engine if the designs change.

## Create split by what you're making (2026-11-08, uncommitted)

Owner ask: Create merged every kind of content into one form; pick the kind up front, fill a couple of short forms,
see a preview sample, then render and export.

| Change | Where |
|---|---|
| Create opens on a chooser: **Quote images**, **Narrated videos**, **Clips from a video**. Each card's picture is real renderer output (three design samples fanned; caption swatches in a 9:16 frame). "All formats" goes back. | `pages/Create.tsx` (`Chooser`) |
| **Quote images** flow, two steps: Quotes (the AI's, or "I have my own": one per line, "— Author" keeps an attribution, max 20, 180 chars) then Design (design swatches, headline font, text position, platforms; Instagram Feed default). Right panel = the batch's first three images in the chosen design with the user's own lines, Auto resolved per piece. | `ImagesForm`, `QuotePreview`, `previews.designs(samples)` |
| **Narrated videos** keeps Brief / Delivery / Look; the Output switch became "Matching feed picture" (video only, or also a 4:5 picture, which shows the design picker). Clips form unchanged. | `VideoForm`, `ClipFormFields` |
| Backend: `brief.quotes` (quantity follows it); the plan sees the list, each piece prompt fixes its quote word for word, and `generate` forces the user's text and author (no repeat check on the user's own lines). Image-only pieces no longer generate narration at render time (no TTS cost or key needed). | `projects.py`, `creative/prompts.py`, `content.py split_author`, `renders.py` |
| `Textarea` primitive. Smoke walks the chooser, the quote-images flow with own quotes (waits for real previews), videos with the 4:5 picture on, and clips via the new card. | `components/ui.tsx`, `scripts/smoke.mjs` |

Fixed on the way: Next on the step before last reused its DOM button as the submit button, so the click created the project early (React re-keyed buttons in `Stepped`). With own quotes the theme is optional (blank = the first quote's opening words). Verified 2026-11-08: `npm test` green (186 backend, typecheck, build, smoke incl. the chooser and quote-images flow), screenshots reviewed.
**Not verified:** a real OpenRouter run with own quotes (the fake model path is tested); Auto in the preview uses
no composition hint, so a real batch can swap designs on even pieces when the writer's hint fits the genre.

## Designed stills and caption styles (2026-11-08, uncommitted)

Owner brief: stills were bland (one Sora block over a scrim, long quotes ran off the bottom) and subtitles had one
look. Reference images: a noir film still with condensed caps, a crumpled-paper note, a whisper line over a scene, a
Swiss "MINDSET" poster. "Think like a high end graphic designer"; subtitles need choices for font, position, everything.

| Change | Where |
|---|---|
| **Seven still designs**, each its own type pairing, grade and texture: noir (mono still, condensed caps, tracked sub-line), paper (crumpled sheet, heavy lowercase printed into it), whisper (one small line, the turn in bold), statement (Swiss poster: big word in reading order, photo rising out of the ground), classic (italic serif, accent quote mark, hairline, name), split (photo over a palette panel, editorial grotesk), stack (fitted condensed capitals). Rules: balanced rags, each sentence on its own line, no lone last word, text sized to fit inside margins, grain under the type, soft shadows only. | `app/design.py`, `render.render_image` |
| Auto picks per piece from the genre (and the writer's composition hint), rotated so a project reads as a series; length limits keep short-copy designs off long quotes. Brief: `image_design`, `image_font` (headline override), `image_position`. | `design.pick`, `projects.CreativeBrief`, `renders.py` |
| Writer returns optional `quote.emphasis` and `quote.kicker` (capped, never fail a piece); heuristics fill in when missing. | `creative/schemas.py`, `creative/prompts.py` |
| **Six caption styles** (karaoke default, unchanged byte for byte; pop, clean, boxed, minimal, serif) with font, position (lower/middle/upper), size, highlight (incl. the project palette) and letter case. Same `CaptionStyle` on write briefs (`captions`) and clip briefs. Key words = quote emphasis + callout words. | `clipper/captions.py`, `renders._subtitles_ass`, `clipper/render_clip.py`, `clips.py` |
| **Create page swatches** drawn by the real renderers over the newest Library picture: `design.previews`, `captions.previews` (libass via ffmpeg). Pickers on the Look step (image design when the output includes images, caption picker when subtitles are on) and on the clip form. | `app/previews.py`, `components/StylePicker.tsx`, `pages/Create.tsx` |
| Fonts: nine OFL families bundled in `assets/fonts` (see DECISIONS.md); Montserrat moved there from the clipper. | `assets/fonts`, `motion.py`, `backend.spec` |

Verified: backend suite (182 + 11 new in `tests/test_design.py`), typecheck, contact sheets of every design on a real
Library photo, caption swatches through real libass, a real `render_video` frame with the pop style in Big Shoulders.
**Not verified:** a real generation end to end (the writer's new `emphasis`/`kicker` fields with OpenRouter), the
Create page pickers by eye in the app, a packaged build with the new fonts. Noticed in passing, not investigated: a
one-off `render_video(still=True, src_duration=0)` with no shot plan produced a 0.92 s video track under 1.6 s audio;
production passes a shot plan, so check a real still-only render.

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
| Keys | One `OPENROUTER_API_KEY` for every AI call (writing, clip selection, transcription, narration) + `PEXELS_API_KEY`; Unsplash optional. Metricool connects with a button (OAuth), no key. DeepSeek/Groq keys removed. | `creative/model.py` (`BASE`, `api_key`), `electron/secrets.ts` |
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
- [ ] Zernio: connect a network in Settings, Posting, post one clip now, schedule another, unschedule a third.

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
