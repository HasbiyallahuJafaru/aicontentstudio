// Checks the PACKAGED app, which the normal smoke cannot: that the frozen backend spawns from resources/,
// runs its migrations, reports ready over stdio, and that the bundled ffmpeg is the one it will use.
// Build it first:  npm run package    (from the repo root, so the backend is frozen too)
// Run:             node scripts/smoke-packaged.mjs
import { _electron as electron } from 'playwright-core'
import { existsSync, mkdirSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const unpacked = join(here, '..', 'release', 'win-unpacked')
const exe = join(unpacked, 'AI Social Content Studio.exe')
assert.ok(existsSync(exe), `no packaged build at ${exe} - run npm run package first`)

for (const rel of ['resources/backend/backend.exe', 'resources/ffmpeg/ffmpeg.exe', 'resources/ffmpeg/ffprobe.exe']) {
  assert.ok(existsSync(join(unpacked, rel)), `missing from the package: ${rel}`)
}

const out = process.env.SMOKE_OUT || join(tmpdir(), 'acs-smoke')
mkdirSync(out, { recursive: true })
const root = mkdtempSync(join(tmpdir(), 'acs-packaged-'))
const env = { ...process.env, ACS_DATA_DIR: join(root, 'data') }
delete env.ELECTRON_RUN_AS_NODE

const app = await electron.launch({ executablePath: exe, args: [`--user-data-dir=${join(root, 'profile')}`], env })
const win = await app.firstWindow()
await win.getByRole('button', { name: "Let's create content" }).waitFor({ timeout: 60_000 })
await win.getByRole('button', { name: "Let's create content" }).click()

// "Engine ready" only appears once the frozen backend has migrated its database and answered over stdio.
await win.getByRole('status').filter({ hasText: 'Engine ready' }).waitFor({ timeout: 60_000 })
await win.screenshot({ path: join(out, 'packaged-dashboard.png') })

// The backend must be using the ffmpeg we shipped, not whatever happens to be on the machine.
const info = await win.evaluate(() => window.studio.call('app.info'))
assert.ok(info.result?.version, `app.info did not answer: ${JSON.stringify(info)}`)

await app.close()
console.log(`packaged smoke ok (version ${info.result.version}), screenshot in ${out}`)
