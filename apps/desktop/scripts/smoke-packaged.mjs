// Checks the PACKAGED app, which the normal smoke cannot: that the frozen backend spawns from resources/,
// runs its migrations, reports ready over stdio, and that the bundled ffmpeg is the one it will use.
// Build it first:  npm run package    (from the repo root, so the backend is frozen too)
// Run:             node scripts/smoke-packaged.mjs
import { _electron as electron } from 'playwright-core'
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const unpacked = process.env.ACS_UNPACKED || join(here, '..', 'release', 'win-unpacked')  // env: a build made elsewhere
const exe = join(unpacked, 'AI Social Content Studio.exe')
assert.ok(existsSync(exe), `no packaged build at ${exe} - run npm run package first`)

for (const rel of ['resources/backend/AI Social Content Studio Engine.exe','resources/ffmpeg/ffmpeg.exe', 'resources/ffmpeg/ffprobe.exe']) {
  assert.ok(existsSync(join(unpacked, rel)), `missing from the package: ${rel}`)
}

// Every exe we ship should be signed once a certificate is configured (CSC_LINK + CSC_KEY_PASSWORD): unsigned
// exes are what antivirus sandboxes. ACS_REQUIRE_SIGNED=1 turns the report into a failure.
const sigs = JSON.parse(execFileSync('powershell', ['-NoProfile', '-Command',
  `Get-ChildItem -LiteralPath '${unpacked}' -Recurse -Filter *.exe | ForEach-Object { [pscustomobject]@{ f = $_.FullName.Substring(${unpacked.length + 1}); s = [string](Get-AuthenticodeSignature -LiteralPath $_.FullName).Status } } | ConvertTo-Json -Compress`,
], { encoding: 'utf8' }))
for (const { f, s } of [sigs].flat()) console.log(`signature ${s.padEnd(9)} ${f}`)
const unsigned = [sigs].flat().filter((x) => x.s !== 'Valid')
if (process.env.ACS_REQUIRE_SIGNED === '1') assert.equal(unsigned.length, 0, `unsigned: ${unsigned.map((x) => x.f).join(', ')}`)

// Motion layers: the packaged exe, run as Node, must render a composition through the unpacked HyperFrames runner
// with the bundled ffmpeg and the GSAP the frozen backend ships (the same path app/motion.py takes).
{
  const comp = mkdtempSync(join(tmpdir(), 'acs-motion-'))
  const gsap = join(unpacked, 'resources', 'backend', '_internal', 'app', 'motion_assets', 'gsap.min.js')
  assert.ok(existsSync(gsap), `missing from the package: ${gsap}`)
  copyFileSync(gsap, join(comp, 'gsap.min.js'))
  writeFileSync(join(comp, 'index.html'), `<!doctype html><html><body style="margin:0;background:transparent">
<div id="root" data-composition-id="probe" data-start="0" data-width="320" data-height="240" data-duration="1">
<div class="clip" data-start="0" data-duration="1" data-track-index="0"><b id="t" style="font:64px sans-serif;color:#fff">HOOK</b></div></div>
<script src="gsap.min.js"></script><script>const tl = gsap.timeline({ paused: true });
tl.from('#t', { opacity: 0, duration: 0.5 }); window.__timelines = { probe: tl };</script></body></html>`)
  const layer = join(comp, 'layer.webm')
  const ff = join(unpacked, 'resources', 'ffmpeg')
  const run = spawnSync(exe, [join(unpacked, 'resources', 'app.asar.unpacked', 'motion', 'render.mjs'), comp, layer], {
    env: { ...process.env, ELECTRON_RUN_AS_NODE: '1', HYPERFRAMES_FFMPEG_PATH: join(ff, 'ffmpeg.exe'),
      HYPERFRAMES_FFPROBE_PATH: join(ff, 'ffprobe.exe'),
      HYPERFRAMES_BROWSER_PATH: process.env.HYPERFRAMES_BROWSER_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe' },
    encoding: 'utf8', timeout: 240_000,
  })
  const result = run.stdout.trim().split('\n').reverse().find((l) => l.startsWith('{')) ?? run.stderr.slice(-800)
  assert.ok(existsSync(layer), `packaged motion render failed: ${result}`)
  console.log(`packaged motion layer ok: ${result}`)
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

// A fresh install has no keys: the setup screens come first. Skip through them (Unsplash and Metricool are optional).
await win.getByRole('heading', { name: 'Connect the AI' }).waitFor({ timeout: 30_000 })
await win.screenshot({ path: join(out, 'packaged-setup.png') })
for (let i = 1; i <= 4; i++) {
  await win.getByText(`Step ${i} of 5`).waitFor()
  await win.getByRole('button', { name: 'Skip for now' }).click()
}
await win.getByRole('heading', { name: 'Almost there' }).waitFor()
await win.getByRole('button', { name: 'Start creating' }).click()

// "Engine ready" only appears once the frozen backend has migrated its database and answered over stdio.
await win.getByRole('status').filter({ hasText: 'Engine ready' }).waitFor({ timeout: 60_000 })
// The Dashboard's main button proves the page itself rendered (motion is on here, so wait out its entrance).
await win.getByRole('button', { name: /Start your first project|New project/ }).waitFor({ timeout: 30_000 })
await win.waitForTimeout(1500)
await win.screenshot({ path: join(out, 'packaged-dashboard.png') })

// The backend must be using the ffmpeg we shipped, not whatever happens to be on the machine.
const info = await win.evaluate(() => window.studio.call('app.info'))
assert.ok(info.result?.version, `app.info did not answer: ${JSON.stringify(info)}`)

await app.close()
console.log(`packaged smoke ok (version ${info.result.version}), screenshot in ${out}`)
