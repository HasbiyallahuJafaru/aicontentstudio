// End-to-end check of the real app (build first: npm run build). Uses a throwaway data + profile folder.
// Screenshots go to SMOKE_OUT (default: <tmp>/acs-smoke). Exit code 1 on any failure.
import { _electron as electron } from 'playwright-core'
import { mkdtempSync, readFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const root = mkdtempSync(join(tmpdir(), 'acs-'))
const out = process.env.SMOKE_OUT || join(tmpdir(), 'acs-smoke')
mkdirSync(out, { recursive: true })
const env = { ...process.env, ACS_DATA_DIR: join(root, 'data') }
delete env.ELECTRON_RENDERER_URL
delete env.ELECTRON_RUN_AS_NODE

async function launch() {
  const app = await electron.launch({ args: ['.', `--user-data-dir=${join(root, 'profile')}`], env })
  const win = await app.firstWindow()
  await win.setViewportSize({ width: 1440, height: 900 })
  await win.emulateMedia({ reducedMotion: 'reduce' })
  await win.getByText('Engine ready').waitFor({ timeout: 30_000 })
  return { app, win }
}
const shot = (win, name) => win.screenshot({ path: join(out, `${name}.png`) })

let { app, win } = await launch()
await win.getByText('No projects yet').waitFor()
await shot(win, '1-dashboard-empty')

await win.keyboard.press('Control+N')
await win.getByRole('heading', { name: 'New project' }).waitFor()
await win.getByText('Intense', { exact: true }).click()
await win.getByText('Video + image').click()
await shot(win, '2-create')
await win.keyboard.press('Control+Enter')
await win.getByRole('complementary', { name: 'Project details' }).waitFor()
assert.equal(await win.getByText('Intense').first().isVisible(), true)
await shot(win, '3-projects')

await win.getByRole('button', { name: 'Settings' }).click()
await win.getByLabel('Pexels API key').fill('smoke-test-key-123')
await win.getByLabel('Pexels API key').press('Enter')
await win.getByText('Saved and encrypted on this computer').waitFor()
await win.getByLabel('Quantity').fill('3')
await win.getByRole('button', { name: 'Save changes' }).click()
await win.getByText('Saved', { exact: true }).waitFor()
await shot(win, '4-settings')
const secretsFile = readFileSync(join(root, 'profile', 'secrets.json'), 'utf8')
assert.ok(secretsFile.includes('PEXELS_API_KEY') && !secretsFile.includes('smoke-test-key-123'), 'key stored encrypted')
await app.close()

;({ app, win } = await launch())
await win.getByRole('heading', { name: 'Recent projects' }).waitFor()
assert.equal(await win.getByText('Discipline').count(), 1, 'project survives restart')
await win.keyboard.press('Control+N')
assert.equal(await win.getByRole('radio', { name: '3', exact: true }).isChecked(), true, 'settings survive restart')
await win.getByRole('button', { name: 'Settings' }).click()
await win.getByText('Saved and encrypted on this computer').waitFor()
await shot(win, '5-dashboard-after-restart')
await app.close()

console.log(`smoke ok, screenshots in ${out}`)
