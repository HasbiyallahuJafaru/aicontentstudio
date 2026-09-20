# AI Social Content Studio: project instructions

Windows desktop app that turns a short brief into finished social videos/images (quote, narration, visuals, palette,
TTS, FFmpeg render, per-platform metadata) and exports them for Metricool. Local only: no accounts, no cloud.

- Spec (source of truth for scope and phase order): `Prd.txt`. Product record: `PRODUCT.md`.
- Dependency/license decisions + machine gotchas: `DECISIONS.md` (update when a dependency changes).
- **Progress and next steps: `.claude/handover.md`. Read it first in every new chat, and update it at the end of
  every phase (or before the chat runs out).**

## Developer identity (for branding + integrations)
- Website: https://hasbiyallahu.xyz · GitHub: https://github.com/HasbiyallahuJafaru ·
  LinkedIn: https://www.linkedin.com/in/hasbiyallahu-jafaru/ · Instagram: TBD (user will supply).
- "Created by" footer (interactive SVG logos for website/LinkedIn/GitHub) goes on every Shell page, and the splash
  gets Instagram+GitHub icons lower-left — see handover Milestone 7 Phase A.

## Product direction (user priority)
North star: turn raw long-form content into polished, platform-ready short-form content with as little manual
editing as possible. Clip quality bar: premium modern Shorts, never "AI-generated looking" — priority order:
story > hook > pacing > clarity > visual quality > audio quality > platform-safe composition > brand consistency.
Backlog + integration statuses (IP routing research, Metricool/Buffer open items, quality roadmap) live in
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
  `tests/`. Milestone 7 adds `app/clipper/` (long-video → shorts engine ported from
  `C:\Users\USER\Documents\ClipperAi\apps\backend\clipper.py` — that repo is the user's; copying code is fine).
- `apps/desktop/` Electron + React. `electron/main.ts` (window, IPC allowlist, media:// protocol),
  `electron/backend.ts` (spawn/supervise Python), `electron/secrets.ts` (safeStorage), `electron/preload.ts` (the
  only renderer API: `window.studio`), `src/lib/studio.ts` (typed calls, hooks, shared constants),
  `src/components/ui.tsx` (all primitives), `src/components/Preview.tsx` (piece preview + regenerate/approve),
  `src/components/Branding.tsx` (developer socials + created-by footer), `src/pages/*` (Splash first, then the
  Shell pages incl. Queue + Exports), `src/styles/index.css` (design tokens).

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
- **Every phase ends with:** `npm test` from the repo root (backend unittest + typecheck + build + smoke), a look at
  the smoke screenshots, `graphify update .`, and an updated `.claude/handover.md`. Never claim something works
  without running it; say plainly what wasn't verified.
- Commit only when the user asks.
