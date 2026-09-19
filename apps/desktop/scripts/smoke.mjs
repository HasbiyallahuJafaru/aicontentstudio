// End-to-end check of the real app (build first: npm run build). Uses a throwaway data + profile folder and a local
// fake DeepSeek server (no paid calls). Screenshots go to SMOKE_OUT (default: <tmp>/acs-smoke). Exit 1 on failure.
import { _electron as electron } from 'playwright-core'
import { createServer } from 'node:http'
import { mkdtempSync, readFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const QUOTES = ['Show up before the feeling does.', 'Small steps still count as moving.', 'The quiet work is the real work.']
const SUBJECTS = ['runner on a mountain ridge at dawn', 'empty city crosswalk at night', 'fog rolling over a still lake']
let piece = 0
const fake = createServer((req, res) => {
  let body = ''
  req.on('data', (c) => (body += c))
  req.on('end', () => {
    const prompt = JSON.parse(body).messages.at(-1).content
    const out = prompt.includes('Plan a batch')
      ? { batch_theme: 'discipline', pieces: SUBJECTS.map((s, i) => ({ angle: ['showing up', 'small habits', 'quiet work'][i], visual_subject: s, visual_type: 'video', intensity: 'medium', narration_style: 'calm reflective' })) }
      : {
          quote: { text: QUOTES[piece % 3], author: null },
          narration: { text: `Nobody sees the early hours. ${QUOTES[piece++ % 3]} Keep going anyway.`, delivery: 'calm_reflective' },
          visual: { preferred_type: 'video', search_query: 'runner mountain ridge sunrise', secondary_query: 'trail runner dawn fog', mood: 'quiet determination' },
          design: { text_density: 'low', animation: 'slow', composition: 'editorial' },
          metadata: { title: 'Before the feeling', description: 'A short reflection on discipline and showing up.', caption: 'Start before you feel ready.',
            hashtags: ['#discipline', '#mindset', '#habits'], keywords: ['discipline', 'habits', 'consistency'], alt_text: 'A lone runner on a ridge at sunrise.' },
        }
    setTimeout(() => res.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify(out) } }] })), 400)
  })
}).listen(0)

const root = mkdtempSync(join(tmpdir(), 'acs-'))
const out = process.env.SMOKE_OUT || join(tmpdir(), 'acs-smoke')
mkdirSync(out, { recursive: true })
const env = { ...process.env, ACS_DATA_DIR: join(root, 'data'), ACS_DEEPSEEK_URL: `http://127.0.0.1:${fake.address().port}` }
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

/** Fails if the window or the main frame scrolls sideways at any of the given sizes (min window is 1024×680). */
async function assertNoHorizontalOverflow(win, page) {
  for (const [width, height] of [[1024, 672], [1280, 672], [1366, 768], [1920, 1080]]) {
    await win.setViewportSize({ width, height })
    await win.waitForTimeout(50)
    const o = await win.evaluate(() => {
      const main = document.querySelector('main')
      const wide = [...document.querySelectorAll('main *')].filter((el) => el.getBoundingClientRect().right > main.getBoundingClientRect().right + 1 && getComputedStyle(el).position !== 'absolute')
      return { doc: document.documentElement.scrollWidth - innerWidth, main: main.scrollWidth - main.clientWidth,
        offender: wide.map((el) => el.tagName + '.' + String(el.className).slice(0, 60))[0] }
    })
    assert.ok(o.doc <= 0 && o.main <= 0, `${page} overflows sideways at ${width}x${height}: ${JSON.stringify(o)}`)
  }
  await win.setViewportSize({ width: 1440, height: 900 })
}

let { app, win } = await launch()
await win.getByText('Your first batch starts here').waitFor()
await shot(win, '1-dashboard-empty')
await assertNoHorizontalOverflow(win, 'dashboard')

// Settings: keys (encrypted) + a default
await win.keyboard.press('Control+,')
for (const [labelText, value] of [['DeepSeek API key', 'sk-smoke-deepseek'], ['Pexels API key', 'smoke-test-key-123']]) {
  await win.getByLabel(labelText).fill(value)
  await win.getByLabel(labelText).press('Enter')
}
await win.getByText('Saved and encrypted on this computer').nth(1).waitFor()
await win.getByLabel('Quantity').fill('3')
await win.getByRole('button', { name: 'Save changes' }).click()
await win.getByText('Saved', { exact: true }).waitFor()
await shot(win, '2-settings')
await assertNoHorizontalOverflow(win, 'settings')
const secretsFile = readFileSync(join(root, 'profile', 'secrets.json'), 'utf8')
assert.ok(secretsFile.includes('PEXELS_API_KEY') && !secretsFile.includes('smoke-test-key-123'), 'keys stored encrypted')

// Create → generate
await win.keyboard.press('Control+N')
await win.getByRole('button', { name: /Create and generate/ }).waitFor()
await win.getByText('Intense', { exact: true }).click()
await shot(win, '3-create')
await assertNoHorizontalOverflow(win, 'create')
await win.keyboard.press('Control+Enter')
await win.getByText(/Writing piece \d of 3|Planning 3 angles/).waitFor({ timeout: 15_000 })
await shot(win, '4-generating')
await win.locator('blockquote').getByText(QUOTES[2]).waitFor({ timeout: 30_000 })
await win.getByRole('button', { name: /Generate again/ }).waitFor()
await shot(win, '5-project-written')
assert.equal(await win.locator('blockquote').count(), 3)
await assertNoHorizontalOverflow(win, 'project')
await app.close()

// Restart: project, pieces, setting and keys persist
;({ app, win } = await launch())
await win.getByRole('heading', { name: 'Recent projects' }).waitFor()
await win.getByText('3 of 3 written').waitFor()
await assertNoHorizontalOverflow(win, 'dashboard with data')
await win.getByText('Discipline').click()
await win.locator('blockquote').getByText(QUOTES[0]).waitFor()
await win.keyboard.press('Control+N')
assert.equal(await win.getByRole('radio', { name: '3', exact: true }).isChecked(), true, 'settings survive restart')
await app.close()
fake.close()

console.log(`smoke ok, screenshots in ${out}`)
