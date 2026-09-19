# AI Social Content Studio

A Windows desktop app that turns a short creative brief into finished social content: original quotes, spoken
narration, chosen visuals, an adapted color palette, platform captions, and (from Milestone 5) rendered video and
image exports for Metricool. Local only: no accounts, no cloud. Your API keys and your content never leave this
machine.

Built by [Hasbiyallahu](https://hasbiyallahu.xyz).

## Status

| Milestone | Scope | State |
|---|---|---|
| 0 | Research and decisions | Done ([DECISIONS.md](DECISIONS.md)) |
| 1 | Electron + React shell, Python stdio backend, SQLite, Settings, projects | Done |
| 2 | DeepSeek generation: batch planning, content schemas, jobs with live progress | Done |
| 3 | Pexels/Unsplash asset pipeline: scoring, dedup, cooldowns, Library | Done |
| 4 | Visual analysis, HEX extraction, palette engine, composition detection | Done |
| 5 | TTS, audio, FFmpeg video/image renderers | Next |
| 6-7 | Preview, regeneration, queue, export, refinement, packaging | Planned |

Milestones 2-4 are verified end to end against local fake servers (see `apps/desktop/scripts/smoke.mjs`); real API
calls need your keys and are the first thing to try once they are set.

## Architecture

- `apps/desktop` - Electron 44 + React 19 + TypeScript + Tailwind CSS 4. The renderer is sandboxed: it talks to the
  backend through one preload bridge and never sees API keys. API keys are encrypted with the OS (safeStorage/DPAPI).
- `apps/backend` - Python 3.12, stdlib + pydantic + httpx + Pillow. JSON lines over stdio, one module per area,
  SQLite with plain SQL migrations. All pipeline logic lives here; the UI never duplicates it.
- Providers: DeepSeek (creative writing), Pexels and Unsplash (visuals). Everything provider-specific stays behind
  small interfaces (`CreativeModel`, `VisualProvider`).
- The spec in [Prd.txt](Prd.txt) is the source of truth for scope; [DECISIONS.md](DECISIONS.md) records dependency
  and license choices; `.claude/handover.md` tracks exact progress.

## Getting started

Requirements: Node 20+, Python 3.12, ffmpeg on PATH (needed from Milestone 5 on).

```bash
npm run setup     # once: Python venv + pip + npm install
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # backend unittest + typecheck + build + end-to-end smoke (fake servers, no paid calls)
```

On this kind of machine with a TLS-inspecting proxy, set `NODE_OPTIONS=--use-system-ca` before network commands.

First run: open Settings, paste your DeepSeek API key (and Pexels/Unsplash keys for visuals), then Create. Keys are
stored encrypted in your user profile and are only ever decrypted by the app itself.

## The splash

The intro clip is open water at 60fps, bundled locally so the app works offline. Credit: "Waves off of dock at
Boston harbor" by Adam S. Keck, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), via Wikimedia
Commons (re-encoded excerpt).
