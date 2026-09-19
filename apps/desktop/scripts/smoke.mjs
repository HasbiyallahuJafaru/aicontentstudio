// End-to-end check of the real app (build first: npm run build). Uses a throwaway data + profile folder and local
// fake DeepSeek + Pexels servers (no paid calls). Screenshots go to SMOKE_OUT (default: <tmp>/acs-smoke). Exit 1 on failure.
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

/** An 8x8 BMP whose stripes repeat every `period` pixels: distinct-looking thumbnails, so each asset hashes differently. */
function bmp(period) {
  const size = 8
  const px = []
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) px.push(...(Math.floor(x / period) % 2 === 0 ? [200, 200, 200] : [40, 40, 40]))
  const pixels = Buffer.from(px)
  const h = Buffer.alloc(54)
  h.write('BM', 0)
  h.writeUInt32LE(54 + pixels.length, 2)
  h.writeUInt32LE(54, 10)
  h.writeUInt32LE(40, 14)
  h.writeInt32LE(size, 18)
  h.writeInt32LE(size, 22)
  h.writeUInt16LE(1, 26)
  h.writeUInt16LE(24, 28)
  h.writeUInt32LE(0, 30)
  h.writeUInt32LE(pixels.length, 34)
  return Buffer.concat([h, pixels])
}

let pexelsBase = ''
const fakePexels = createServer((req, res) => {
  const url = new URL(req.url, pexelsBase)
  if (url.pathname === '/videos/search') {
    res.end(JSON.stringify({
      videos: [1, 2, 3].map((id) => ({
        id, width: 1080, height: 1920, url: `https://pexels.example/video/${id}`, duration: 10 + id,
        image: `${pexelsBase}/thumb/${id}.bmp`, user: { name: `Creator ${id}` },
        video_files: [
          { file_type: 'video/mp4', width: 1920, height: 1080, fps: 60.0, link: `${pexelsBase}/asset/${id}-landscape.mp4` },
          { file_type: 'video/mp4', width: 1080, height: 1920, fps: 30.0, link: `${pexelsBase}/asset/${id}.mp4` },
        ],
      })),
    }))
  } else if (url.pathname.startsWith('/thumb/')) {
    res.setHeader('Content-Type', 'image/bmp')
    res.end(bmp(Number(url.pathname.match(/(\d)/)[1])))
  } else if (url.pathname.startsWith('/asset/')) {
    res.setHeader('Content-Type', 'video/mp4')
    res.end(bmp(Number(url.pathname.match(/(\d)/)[1]))) // bytes are never decoded: only the thumbnail is hashed
  } else {
    res.statusCode = 404
    res.end()
  }
}).listen(0)
pexelsBase = `http://127.0.0.1:${fakePexels.address().port}`

const root = mkdtempSync(join(tmpdir(), 'acs-'))
const out = process.env.SMOKE_OUT || join(tmpdir(), 'acs-smoke')
mkdirSync(out, { recursive: true })
const env = { ...process.env, ACS_DATA_DIR: join(root, 'data'), ACS_DEEPSEEK_URL: `http://127.0.0.1:${fake.address().port}`,
  ACS_PEXELS_URL: pexelsBase }
delete env.ELECTRON_RENDERER_URL
delete env.ELECTRON_RUN_AS_NODE

async function launch() {
  const app = await electron.launch({ args: ['.', `--user-data-dir=${join(root, 'profile')}`], env })
  const win = await app.firstWindow()
  await win.setViewportSize({ width: 1440, height: 900 })
  await win.emulateMedia({ reducedMotion: 'reduce' })
  await win.getByRole('button', { name: "Let's create content" }).waitFor({ timeout: 30_000 })
  return { app, win }
}

async function enterApp(win) {
  await win.getByRole('button', { name: "Let's create content" }).click()
  await win.getByText('Engine ready').waitFor({ timeout: 30_000 })
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

/** Splash has no <main>; check the app root the same way at two sizes. */
async function assertNoHorizontalOverflowOnSplash(win) {
  for (const [width, height] of [[1024, 672], [1440, 900]]) {
    await win.setViewportSize({ width, height })
    await win.waitForTimeout(50)
    const o = await win.evaluate(() => {
      const root = document.querySelector('#root > div')
      return { doc: document.documentElement.scrollWidth - innerWidth, inner: root ? root.scrollWidth - root.clientWidth : 0 }
    })
    assert.ok(o.doc <= 0 && o.inner <= 0, `splash overflows sideways at ${width}x${height}: ${JSON.stringify(o)}`)
  }
  await win.setViewportSize({ width: 1440, height: 900 })
}

let { app, win } = await launch()
await win.getByText('Meet our developer').waitFor()
await shot(win, '0-splash')
await assertNoHorizontalOverflowOnSplash(win)
await enterApp(win)
await win.getByRole('heading', { name: 'New project' }).waitFor()
await shot(win, '1-create-empty')
await assertNoHorizontalOverflow(win, 'create')

// Settings: keys (encrypted) + a default
await win.keyboard.press('Control+,')
for (const [labelText, value] of [['DeepSeek API key', 'sk-smoke-deepseek'], ['Pexels API key', 'smoke-test-key-123']]) {
  await win.getByLabel(labelText).fill(value)
  await win.getByLabel(labelText).press('Enter')
}
await win.getByText('Saved and encrypted on this computer').nth(1).waitFor()
await win.getByLabel('Quantity').fill('3')
await win.getByLabel('Asset cooldown').fill('7')
await win.getByRole('button', { name: 'Save changes' }).click()
await win.getByText('Saved', { exact: true }).waitFor()
await shot(win, '2-settings')
await assertNoHorizontalOverflow(win, 'settings')
const secretsFile = readFileSync(join(root, 'profile', 'secrets.json'), 'utf8')
assert.ok(secretsFile.includes('PEXELS_API_KEY') && !secretsFile.includes('smoke-test-key-123'), 'keys stored encrypted')

// Library before anything exists
await win.getByRole('button', { name: 'Library' }).click()
await win.getByText('No assets yet').waitFor()
await shot(win, '3-library-empty')

// Create → generate (pieces + visuals)
await win.keyboard.press('Control+N')
await win.getByRole('button', { name: /Create and generate/ }).waitFor()
await win.getByText('Intense', { exact: true }).click()
await win.keyboard.press('Control+Enter')
await win.getByText(/Writing piece \d of 3|Planning 3 angles/).waitFor({ timeout: 15_000 })
await shot(win, '4-generating')
await win.locator('blockquote').getByText(QUOTES[2]).waitFor({ timeout: 30_000 })
await win.getByRole('button', { name: /Generate again/ }).waitFor()
await shot(win, '5-project-written')
assert.equal(await win.locator('blockquote').count(), 3)
await assertNoHorizontalOverflow(win, 'project')

// Library: three downloaded videos with thumbnails, usage counts, and working filters
await win.getByRole('button', { name: 'Library' }).click()
await win.getByText('Pexels · Video').first().waitFor()
assert.equal(await win.getByText('Pexels · Video').count(), 3)
assert.equal(await win.getByText('1080 × 1920').count(), 3)
await win.getByText('Used 1 time').first().waitFor()
assert.ok(await win.locator('main span[title^="#"]').count() >= 3, 'dominant color swatches shown')
await shot(win, '6-library')
await assertNoHorizontalOverflow(win, 'library')
const choose = (legend, option) =>
  win.locator('fieldset').filter({ hasText: legend }).getByText(option, { exact: true }).click()
await choose('Usage', 'Never used')
await win.getByText('No assets match these filters.').waitFor()
await choose('Usage', 'All')
await choose('Type', 'Images')
await win.getByText('No assets match these filters.').waitFor()
await choose('Type', 'All')
await app.close()

// Restart: project, pieces, assets and settings persist
;({ app, win } = await launch())
await enterApp(win)
await win.getByRole('button', { name: 'Dashboard' }).click()
await win.getByRole('heading', { name: 'Recent projects' }).waitFor()
await win.getByText('3 of 3 written').waitFor()
await assertNoHorizontalOverflow(win, 'dashboard with data')
await win.getByText('Discipline').click()
await win.locator('blockquote').getByText(QUOTES[0]).waitFor()
await win.getByRole('button', { name: 'Library' }).click()
await win.getByText('Pexels · Video').first().waitFor()
assert.equal(await win.getByText('Pexels · Video').count(), 3, 'assets survive restart')
await shot(win, '7-library-restart')
await win.keyboard.press('Control+N')
assert.equal(await win.getByRole('radio', { name: '3', exact: true }).isChecked(), true, 'settings survive restart')
await app.close()
fake.close()
fakePexels.close()

console.log(`smoke ok, screenshots in ${out}`)
