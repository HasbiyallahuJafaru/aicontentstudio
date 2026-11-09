# YT Clipper - AI Content Studio

A free Windows desktop app that turns long videos into captioned shorts, and a short topic into quote images and
narrated videos, then posts or schedules all of it to your social accounts. It runs on your own PC: no account, no
cloud, no subscription. Your keys and your content stay on your machine.

**Download:** [ytclipper.xyz](https://ytclipper.xyz) · Built by [Hasbiyallahu Jafaru](https://hasbiyallahu.xyz)

## What it makes

**Clips from a video.** Paste a YouTube link or pick a file on your computer. The app transcribes every word, finds
the moments that stand on their own, and cuts each one into a vertical short of at least a minute. Dead air and
filler words come out, the crop follows the speaker's face, the strongest line can play first as a cold open, and
captions are burned in in the style you pick. Every clip comes with its own title, hook and post copy for each
network.

**Quote images.** Give it a topic and a genre, or bring your own quotes (typed, pasted, or imported from a CSV, with
a sample file and a ready-made AI prompt for writing one). Every quote is a real, documented line with its author.
Each image is laid out in one of 13 typographic designs (noir film still, paper note, Swiss poster, risograph print,
instant photo and more) over a stock photo picked to match.

**Narrated videos.** The same brief becomes a spoken short: a script written hook-first, read by a Gemini voice you
choose, cut across several stock shots with the genre's colour grade, film grain and optional karaoke subtitles.

Before anything full-size downloads, you see the footage the app proposes as thumbnails and keep or swap each pick.
**Download and render** then fetches exactly those and renders every piece on one progress bar, with a step-by-step
log that shows which piece and which step is running, finished or failed.

**Posting.** Connect your accounts once through [Zernio](https://zernio.com) (free for the first two). Post a single
clip or image, or press **Schedule all**: choose the first post time and a spacing (every 10 minutes, 15 minutes,
hour, day or other day), adjust any single time, and send the whole batch. Each item then shows Scheduled, Posted or
Failed. Or export a folder with the files and per-platform captions and upload them yourself.

## Genres

Content is organised by format rather than mood, because that is how the platforms reward it. Each genre has its own
quote voices, narration style and edit grammar.

| Genre | Quotes from | Cut |
|---|---|---|
| Hope | Keller, Dickinson, Whitman, Hugo, Emerson, Tagore | 2.6-3.2 s shots, dissolves, warm lift and halation |
| Hard Truth | Roosevelt, Douglass, Seneca, Epictetus, Nietzsche | 1.4-1.9 s shots, hard cuts, bleach bypass, coarse grain |
| Stoic Wisdom | Marcus Aurelius, Seneca, Epictetus, Musonius Rufus | 3.0-4.0 s holds, mostly locked off, cold and desaturated |
| Historical Voices | Documented words of public-domain figures | 2.4-3.0 s, black beats between shots, sepia, heavy grain |
| Book Wisdom | Lines from public-domain classics | 2.6-3.2 s, alternating dissolves, warm paper mids |
| Cinematic Minimal | Lao Tzu, Basho, Rumi, Thoreau, Muir, Rilke | 3.5-4.5 s, fade to black, teal-orange, letterbox, one speed ramp |

Quotes are never invented: every one is a real public-domain line (published before 1929) with its author named.

## How it edits

Renders are meant to look edited, not illustrated. A narrated piece cuts between several distinct shots (different
subject, different place) on the breaths in the narration, using real word timings. Stills get a slow push, every
join is a proper transition, and the whole timeline gets one grade so unrelated stock footage reads as one film.
Music ducks under the voice. A render that opens on a black frame fails its own quality check. The director's spec is
in [.claude/edit-grammar.md](.claude/edit-grammar.md).

## Status

Version 0.1.0 is released and downloadable from [ytclipper.xyz](https://ytclipper.xyz) (Windows, about 256 MB,
unsigned for now, so Windows SmartScreen asks once on first run).

The pipeline is covered by 224 backend tests and an end-to-end smoke run that drives the real app against local
fake services (`apps/desktop/scripts/smoke.mjs`), plus a check of the packaged build. Real-key runs (OpenRouter,
Pexels, Zernio) are verified in part; [NEXT_STEPS.md](NEXT_STEPS.md) lists exactly what has and has not been tried
for real.

## Architecture

- `apps/desktop`: Electron 44, React 19, TypeScript, Tailwind CSS 4. The renderer is sandboxed and reaches the
  backend through one preload bridge (`window.studio`). It never sees an API key; keys are encrypted at rest with
  Windows DPAPI (safeStorage).
- `apps/backend`: Python 3.12 (stdlib plus pydantic, httpx, Pillow, opencv-python, yt-dlp). JSON lines over stdio,
  one module per area, SQLite with plain SQL migrations. All pipeline logic lives here; the UI never duplicates it.
  - `app/creative/` writes (OpenRouter), `app/assets/` finds and scores footage (Pexels, Unsplash), `app/design.py`
    lays out the quote images, `app/edit.py` is the edit grammar, `app/renders.py` plans shots and `app/render.py`
    drives ffmpeg.
  - `app/clipper/` is the long-video engine: download, Whisper transcription, two-pass moment selection, face-tracked
    crop, tightening, captions.
  - `app/motion.py` renders animated hook titles and callouts with HyperFrames (HTML through Edge or Chrome) and
    composites them over the edit.
  - `app/publish/` posts and schedules through Zernio's API and keeps our record of every post.
- `apps/site`: the landing site at ytclipper.xyz (Vite, TypeScript, three.js, GSAP), deployed on Vercel.
- `apps/download-worker`: a Cloudflare Worker that serves the installer from a private R2 bucket after a Turnstile
  check.
- Provider-specific code sits behind small interfaces: `CreativeModel`, `VisualProvider`, `TTSProvider`, `Renderer`,
  `Publisher`.
- ffmpeg always runs as a subprocess with argument arrays, never shell strings, with a stall watchdog so a hung
  encode cannot wedge a job.

## Getting started

Requirements: Node 20+, Python 3.12, and ffmpeg on PATH.

```bash
npm run setup     # once: Python venv + pip + npm install
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # backend tests + typecheck + build + end-to-end smoke (fake servers, no paid calls)
```

Behind a TLS-inspecting proxy, set `NODE_OPTIONS=--use-system-ca` before any network command, including the first
package (electron-builder downloads its toolchain).

To build the Windows installer:

```bash
npm run package          # freezes the backend, bundles ffmpeg, writes the NSIS installer
npm run smoke:packaged   # launches the built app and checks the frozen backend comes up
```

The installer is per-user, lets you choose the folder, and keeps your data on uninstall. It ships its own ffmpeg, so
an installed copy needs nothing else on the machine. The full release steps (signing, upload, site deploy) are in
[.claude/CLAUDE.md](.claude/CLAUDE.md).

## Keys

The app opens without any key; first run walks you through each one, and every step can be skipped.

| Key | Unlocks |
|---|---|
| OpenRouter | Every AI call: writing, clip selection, Whisper transcription and word timings, and the narration voice |
| Pexels (Unsplash optional) | Stock footage and photos for quote images and narrated videos |
| Zernio | Posting and scheduling to your social accounts. Optional; each account is then a browser sign-in |

Models are set in Settings, AI, as OpenRouter ids: `deepseek/deepseek-v4-pro` writes and
`deepseek/deepseek-v4.1-flash` scans transcripts. Transcription uses `openai/whisper-large-v3-turbo`. Narration is
Google's Gemini TTS (`google/gemini-3.8-flash-tts`) through the same OpenRouter key, with 18 voices; a 30 s narration
costs well under a cent.

## Documentation

- [NEXT_STEPS.md](NEXT_STEPS.md): current progress, what is verified, what is next.
- [Prd.txt](Prd.txt): the source of truth for scope and phase order. [PRODUCT.md](PRODUCT.md): the product record.
- [DECISIONS.md](DECISIONS.md): dependency and licence choices, and machine-specific gotchas.
- [.claude/edit-grammar.md](.claude/edit-grammar.md): the director's spec for how a piece is cut.

## Licence

The app is free to use under the [YT Clipper License Agreement](https://ytclipper.xyz/license). The source code in
this repository has no open-source licence, so all rights are reserved. Third-party components and their licences
are listed at [ytclipper.xyz/open-source](https://ytclipper.xyz/open-source).
