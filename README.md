# AI Social Content Studio

A Windows desktop app that turns a short brief, or a long video you already have, into finished short-form
content: written lines, spoken narration, cut and graded footage, burned captions, and per-platform copy ready to
post. Local only. No accounts, no cloud, no subscription. Your API keys and your content never leave this machine.

Built by [Hasbiyallahu](https://hasbiyallahu.xyz).

## Two ways in

**Write content.** Give it a topic and a genre. It plans a batch, writes each piece hook-first, picks a pool of
stock shots, speaks the narration, cuts the video, and writes the caption, hashtags and metadata for every platform
you targeted.

**Clip from video.** Give it a YouTube URL or a local file. It transcribes the whole thing, scans the transcript
for moments that stand alone, ranks them, tracks the speaker's face to reframe 16:9 into 9:16, burns karaoke
captions, and writes native post copy per network.

Both land in the same review flow: preview, redo any single part, approve, export, publish.

## Genres, not tones

Content is organised by format rather than mood, because that is how the platforms actually reward it. Each genre
carries its own writing voice and its own edit grammar.

| Genre | Voice | Cut |
|---|---|---|
| Hope | Hopecore spoken word, a letter to the listener's 2am self | 2.6-3.2s shots, dissolves throughout, warm lift and halation |
| Hard Truth | Speech-edit energy, second person, escalating | 1.4-1.9s shots, hard cuts, bleach bypass, coarse grain |
| Stoic Wisdom | Marcus Aurelius at night, plain declaratives | 3.0-4.0s holds, mostly locked off, cold and desaturated |
| Historical Voices | Documented public-domain lines, attributed | 2.4-3.0s, black beats between shots, sepia and heavy grain |
| Book Wisdom | Public-domain classics bridged into an ordinary day | 2.6-3.2s, alternating dissolves, warm paper mids |
| Cinematic Minimal | The visuals carry it, words land like titles | 3.5-4.5s, fade to black, teal-orange, letterbox bars, one speed ramp |

Attributed genres quote real, documented, pre-1929 sources and name the author. Everything else is original.

## How it edits

The renders are meant to look edited, not illustrated. A piece is cut between a pool of distinct visuals rather
than one clip panning: different subject, different location, mixed literal / metaphorical / atmospheric registers.
Cuts land on breaths in the narration, not on a divisor, using real word timings. Every join is an `xfade`, stills
are supersampled before the Ken Burns move so they do not stair-step, the turn shot can ramp, and the whole
timeline gets one grade so unrelated stock reads as one film. Music ducks under the voice. A render that opens on
a black frame fails its own quality check.

The full spec, including the reference research and the ffmpeg capability audit, is in
[.claude/edit-grammar.md](.claude/edit-grammar.md).

## Status

| Milestone | Scope | State |
|---|---|---|
| 0 | Research and decisions | Done ([DECISIONS.md](DECISIONS.md)) |
| 1 | Electron + React shell, Python stdio backend, SQLite, Settings, projects | Done |
| 2 | DeepSeek generation: batch planning, content schemas, jobs with live progress | Done |
| 3 | Pexels/Unsplash asset pipeline: scoring, dedup, cooldowns, Library | Done |
| 4 | Visual analysis, HEX extraction, palette engine, composition detection | Done |
| 5 | TTS, audio mixing, FFmpeg video and image renderers | Done |
| 6 | Preview, per-part regeneration, queue, export | Done |
| 7 | Branding, long-video clipper, Buffer and Metricool publishing, genres, director-cut renders | Done |
| 8 | Packaging and installer | Done |

Everything is verified end to end against local fake servers (`apps/desktop/scripts/smoke.mjs`) plus 135 backend
tests. Real-key runs against DeepSeek, Pexels, Groq and Buffer are the user's own verification rounds and are
still in progress, so treat output quality claims as unproven until you have run your own keys through it.

## Architecture

- `apps/desktop` - Electron 44, React 19, TypeScript, Tailwind CSS 4. The renderer is sandboxed and reaches the
  backend through a single preload bridge (`window.studio`). It never sees an API key. Keys are encrypted at rest
  with the OS (safeStorage / DPAPI).
- `apps/backend` - Python 3.12, stdlib plus pydantic, httpx, Pillow, opencv-python, yt-dlp, kokoro-onnx. JSON
  lines over stdio, one module per area, SQLite with plain SQL migrations. All pipeline logic lives here; the UI
  never duplicates it.
- `app/edit.py` is the edit grammar, `app/renders.py` plans the shots, `app/render.py` drives ffmpeg.
  `app/clipper/` is the long-video engine, `app/publish/` is Buffer and Metricool.
- Anything provider-specific sits behind a small interface: `CreativeModel`, `VisualProvider`, `TTSProvider`,
  `Renderer`, `Publisher`.
- ffmpeg always runs as a subprocess with argument arrays, never shell strings, with a stall watchdog so a hung
  encode cannot wedge a job.

## Getting started

Requirements: Node 20+, Python 3.12, and ffmpeg on PATH.

```bash
npm run setup     # once: Python venv + pip + npm install
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # backend unittest + typecheck + build + end-to-end smoke (fake servers, no paid calls)
```

Behind a TLS-inspecting proxy, set `NODE_OPTIONS=--use-system-ca` before any network command. electron-builder
downloads its toolchain on the first package, so it needs that too.

To build the Windows installer:

```bash
npm run package          # freezes the backend, bundles ffmpeg, writes apps/desktop/release/*.exe
npm run smoke:packaged   # launches the built app and checks the frozen backend comes up
```

The installer is per-user, lets you choose the folder, and leaves your data behind on uninstall. It ships its own
ffmpeg, so an installed copy needs nothing else on the machine. It is large (around 310 MB) because a frozen
Python runtime and a static ffmpeg are both in the box.

## Keys

Open Settings on first run. Nothing is required to launch the app, and each key unlocks one thing:

| Key | Unlocks |
|---|---|
| DeepSeek | Writing: batch plans, quotes, narration, per-platform copy |
| Pexels or Unsplash | Stock footage and photos for written pieces |
| Groq | Transcription for clip projects, and real word timings for karaoke captions |
| Buffer | Scheduling and publishing, via OAuth. Optional |
| Metricool | Publishing through the Metricool MCP. Optional |

Narration is local and free by default (Kokoro, an 82M on-device voice model), with Windows SAPI as a fallback.
Keys are stored encrypted in your user profile and are only ever decrypted by the app itself.

## Documentation

- [Prd.txt](Prd.txt) is the source of truth for scope and phase order.
- [DECISIONS.md](DECISIONS.md) records dependency and license choices, and the machine-specific gotchas.
- [.claude/edit-grammar.md](.claude/edit-grammar.md) is the director's spec for how a piece is cut.
- `.claude/handover.md` tracks exact progress, what is verified and what is not.

## The splash

The intro clip is open water at 60fps, bundled locally so the app works offline. Credit: "Waves off of dock at
Boston harbor" by Adam S. Keck, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), via Wikimedia
Commons (re-encoded excerpt).
