# Handover

Last updated: 2026-09-19. Read this first in a new chat, then `.claude/CLAUDE.md` rules. Update it after every phase.

## Where things stand

| PRD milestone | State |
|---|---|
| Phase 0 research | Done: `DECISIONS.md` |
| **Milestone 1**: Electron shell, React, Python process, SQLite, Settings, basic project creation (PRD phases 1–5) | **Done, verified** (below) |
| Milestone 2: DeepSeek, content schemas, content generation, project persistence of pieces | **Next** |
| M3 Pexels/Unsplash, asset library, dedup · M4 visual analysis, palette · M5 TTS, audio, FFmpeg renderers · M6 preview, regeneration, queue, export · M7 UI refinement pass · packaging | Not started |

## What exists (Milestone 1)

**Backend** (`apps/backend`, Python 3.12 venv in `.venv`, only dep pydantic):
- stdio JSON-lines RPC (`app/rpc.py`): request `{id, method, params}` → `{id, result}` or
  `{id, error: {message, detail}}`; events `{event, data}` (only `backend.ready` so far). Requests run on a
  4-thread pool. Logs go to stderr as JSON lines (Electron writes them to `<data>/logs/backend.log`).
- Methods: `app.info`, `settings.get`, `settings.update`, `projects.create|list|get|delete`, `secrets.load` (main-only).
- SQLite at `<data>/app.db`, migrations via `PRAGMA user_version`. Tables: `projects` (id, name, status, brief JSON,
  created_at, updated_at), `settings` (key → JSON; key `app` holds the `Settings` pydantic model).
- `CreativeBrief` pydantic model (topic, tone, mood, audience, format, quantity 1–20, platforms ≥1) in `projects.py`.
- `UserError(message, detail)` = human-readable error; the UI shows `detail` under "View technical details".
- Data dir: `ACS_DATA_DIR` env (Electron sets it) else `<repo>/data`. Packaged: `userData/data`.

**Desktop** (`apps/desktop`):
- Electron main starts Python (`.venv\Scripts\python.exe main.py`), restarts it up to 3×/min on crash, then shows
  "Engine stopped" + Restart button; dev mode restarts it when `app/*.py|sql` changes. Stops it on quit.
- IPC: renderer can call any backend method except `secrets.*`. API keys (DeepSeek, Pexels, Unsplash) are
  encrypted with `safeStorage` in `userData/secrets.json` and pushed to Python memory on every backend start/change.
- Screens: Dashboard (recent projects / empty state), Create (brief form + live batch preview of frames at real
  aspect ratios; Ctrl+Enter), Projects (list + detail pane, delete with confirm or Delete key), Settings (API keys,
  AI model/temperature/max tokens, content defaults, media folder + Open). Shortcuts: Ctrl+N new, Ctrl+, settings.
- Design: dark neutral "grading suite", Segoe UI Variable, one amber accent for activity/focus, off-white primary
  button. Tokens in `src/styles/index.css`; primitives in `src/components/ui.tsx`.
- "Create project" saves a **draft** only; the UI says AI generation isn't connected yet.

**Verified 2026-09-19:** backend `python -m unittest` 6/6 (includes real stdio process test); `tsc --noEmit` clean;
`electron-vite build` ok; `npm run smoke` passes: engine starts, create project, save API key (checked encrypted
on disk), change a setting, restart app → project, setting and key all persist. Screenshots reviewed once.

**Not verified:** backend crash → auto-restart path; `npm run dev` HMR (only production build was run);
window sizes other than 1440×900; long text in project names.

## How to run
```bash
npm run setup     # once: venv + pip + npm install (set NODE_OPTIONS=--use-system-ca first on this machine)
npm run dev       # Electron + Vite HMR + Python auto-restart
npm test          # unittest + typecheck + build + smoke (screenshots → %TEMP%/acs-smoke)
graphify update . # refresh the code map after changes
```

## Next: Milestone 2 (DeepSeek + content generation)
1. Migration `002`: `content_pieces` (id, project_id FK cascade, idx, status, creative_angle, quote, narration,
   visual query JSON, design hints JSON, metadata JSON, created_at) + `quote_history` or reuse pieces for similarity.
2. `app/creative/`: `CreativeModel` interface + `DeepSeekModel` (httpx, JSON mode, schema-validated, repair once
   then regenerate, bounded retries with backoff, human errors like "DeepSeek authentication failed. Check your key
   in Settings."). Batch plan first (angles + visual diversity, PRD §75–76), then each piece.
3. Quote dedup against recent history (stdlib `difflib` ratio first; ponytail note on ceiling).
4. Jobs: `generation_jobs` table + job runner emitting `job.started/progress/stage/completed/failed` events;
   cancel flag. UI: project page shows pieces as they arrive with real stage progress; "Generate" replaces the draft note.
5. Tests with a fake DeepSeek (no paid calls): schema validation, invalid JSON repair, dedup, batch diversity.
6. Then add Queue to the sidebar (it has real content once jobs exist).

## Open decisions / notes
- Sidebar only shows built screens; Library, Queue, Exports are added by the milestone that fills them.
- Media folder is shown read-only; choosing another folder (PRD §37) needs a move/migrate step, planned for later.
- Git: `main` pushed to https://github.com/HasbiyallahuJafaru/aicontentstudio (Milestone 1 = commit b53f78b).
  Commit/push only when the user asks.
