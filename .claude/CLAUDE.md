# AI Social Content Studio: project instructions

Windows desktop app that turns a short brief into finished social videos/images (quote, narration, visuals, palette,
TTS, FFmpeg render, per-platform metadata) and exports them for Metricool. Local only: no accounts, no cloud.

- Spec (source of truth for scope and phase order): `Prd.txt`. Product record: `PRODUCT.md`.
- Dependency/license decisions + machine gotchas: `DECISIONS.md` (update when a dependency changes).
- **Progress and next steps: `.claude/handover.md`. Read it first in every new chat, and update it at the end of
  every phase (or before the chat runs out).**

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
  area (`projects.py`, `settings.py`, later `content/`, `assets/`, …), `app/migrations/NNN_*.sql`, `tests/`.
- `apps/desktop/` Electron + React. `electron/main.ts` (window, IPC allowlist), `electron/backend.ts` (spawn/supervise
  Python), `electron/secrets.ts` (safeStorage), `electron/preload.ts` (the only renderer API: `window.studio`),
  `src/lib/studio.ts` (typed calls, hooks, shared constants), `src/components/ui.tsx` (all primitives),
  `src/pages/*`, `src/layouts/Shell.tsx`, `src/styles/index.css` (design tokens).

## Working rules
- **Ponytail:** laziest solution that works. Stdlib/native first, no one-implementation interfaces unless the PRD
  demands the abstraction (it does for CreativeModel, VisualProvider, TTSProvider, Renderer, Publisher). Mark
  deliberate corner-cutting with a `ponytail:` comment naming the ceiling. Never cut validation, security, data safety.
- **UI (taste + impeccable):** use the tokens and primitives; no one-off styles, no em dashes in UI copy, no eyebrow
  labels, no metric-card walls, no fake data or placeholder buttons for core features. Honest progress only.
- **Python is the source of truth** for pipeline logic; TypeScript never duplicates it. Renderer never sees API keys.
- **Every phase ends with:** `npm test` from the repo root (backend unittest + typecheck + build + smoke), a look at
  the smoke screenshots, `graphify update .`, and an updated `.claude/handover.md`. Never claim something works
  without running it; say plainly what wasn't verified.
- Commit only when the user asks.
