# Phase 0: Decisions

Component, license and integration choices. **Used** = in the code now. **Plan** = chosen, verify license/version
when that phase starts. Update this table whenever a dependency changes.

| Component | Choice | License | Status / notes |
|---|---|---|---|
| Desktop shell | Electron 44 | MIT | **Used.** `contextIsolation`, `sandbox`, no `nodeIntegration`; hidden title bar + native Window Controls Overlay. |
| Build tool | electron-vite 5 + Vite 7 | MIT | **Used.** electron-vite 5 supports Vite ≤7 only (not 8). Entries must be absolute paths (relative `electron/…` is treated as the external `electron` package). |
| UI | React 19 + TypeScript 5.9 + Tailwind CSS 4 (`@tailwindcss/vite`) | MIT / Apache-2.0 / MIT | **Used.** No component kit: ~6 own primitives in `src/components/ui.tsx`. shadcn/Radix only if a real need (dialogs, menus) appears. |
| Icons | Phosphor (`@phosphor-icons/react`) | MIT | **Used.** One family. |
| Animation | CSS keyframes/transitions | n/a | **Used.** Motion (framer) only if CSS can't do a specific interaction. |
| UI fonts | Sora Variable (display) + Geist Variable (body) via `@fontsource-variable/*`, bundled by Vite | OFL-1.1 | **Used** (redesign 2026-09-19, user's reference: warm glass, wide display type). Output-render fonts still need vendoring in `assets/fonts` in Phase 10. |
| Electron ↔ Python | JSON lines over stdin/stdout | n/a | **Used** (user choice 2026-09-19). No port, no token, nothing else on the machine can reach it. Events = lines without `id`. |
| Backend runtime | Python 3.12, stdlib + pydantic 2 | MIT | **Used.** Threads (ThreadPoolExecutor) for request concurrency. |
| Database | SQLite via stdlib `sqlite3`, plain `migrations/NNN_*.sql`, `PRAGMA user_version` | Public domain | **Used** (user choice 2026-09-19 over SQLAlchemy/SQLModel). Tables added by the phase that first uses them. WAL mode. |
| API keys | Electron `safeStorage` (DPAPI) → `userData/secrets.json`, pushed to Python memory via `secrets.load` | MIT | **Used.** Renderer only sees set/not-set. Dev fallback: repo `.env`. |
| E2E check | playwright-core `_electron` (`apps/desktop/scripts/smoke.mjs`) | Apache-2.0 | **Used.** No browser download needed. |
| LLM | DeepSeek (OpenAI-compatible `/chat/completions`), JSON mode, via `httpx` 0.28 (BSD-3) | API | **Used (M2).** `verify=ssl.create_default_context()` so the Windows cert store is used (certifi fails behind this machine's TLS-inspecting CA). Model default `deepseek-flash` (setting). Empty content → retry; invalid JSON → repair once → regenerate once; 3 HTTP retries with backoff. `ACS_DEEPSEEK_URL` env overrides the base URL (used by the smoke test's fake server). **Not yet called against the real API.** |
| Visual providers | Pexels API, Unsplash API via `httpx` | API | **Plan (M3).** Store creator, source URL, asset id, license text for attribution. Verify current terms for automated/commercial use before production. Unsplash requires attribution + download-tracking ping. |
| Perceptual hash | own dHash/pHash with Pillow (~15 lines) | HPND (Pillow) | **Plan (M3).** `imagehash` (BSD-2) only if own version falls short. |
| Visual analysis / palette | OpenCV (`opencv-python-headless`) k-means + own scoring | Apache-2.0 | **Plan (M4).** |
| TTS | Candidates: Kokoro-82M via `kokoro-onnx` (Apache-2.0 weights, MIT lib, CPU, Windows OK); Piper (`piper1-gpl` is GPL-3.0; the MIT original is archived) | see left | **Plan (M5).** Kokoro first. Behind a `TTSProvider` interface as the PRD requires. |
| Rendering | FFmpeg CLI (subprocess, argument arrays) | LGPL/GPL build-dependent | **Plan (M5).** Separate process, no linking. Must be bundled in the installer. Dev machine has 9.0.1 on PATH. |
| Music | User-supplied licensed tracks + metadata | per track | **Plan.** Never auto-download. |
| Packaging | electron-builder (NSIS) + PyInstaller-frozen backend in `resources/backend` | MIT / GPL with bootloader exception | **Plan (packaging).** `electron/backend.ts` already expects `resources/backend` when packaged but still launches `python main.py`; switch to the frozen exe then. |

## Environment gotchas (this machine)

- A local TLS-inspecting CA: Node needs `NODE_OPTIONS=--use-system-ca` for npm/network (`npm install`, Electron download).
- npm 11 blocks install scripts; `apps/desktop/package.json` `allowScripts` approves electron + esbuild. If
  `node_modules/electron/dist` is missing: `node node_modules/electron/install.js` (retry; downloads are flaky).
- VS Code terminals set `ELECTRON_RUN_AS_NODE=1`, which makes Electron run as plain Node (`app` is undefined).
  `npm run dev|start|smoke` strip it (`scripts/electron-vite.mjs`).
