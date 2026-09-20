// End-to-end check of the real app (build first: npm run build). Uses a throwaway data + profile folder and local
// fake DeepSeek + Pexels servers (no paid calls). Screenshots go to SMOKE_OUT (default: <tmp>/acs-smoke). Exit 1 on failure.
import { _electron as electron } from 'playwright-core'
import { createServer } from 'node:http'
import { mkdtempSync, readFileSync, readdirSync, mkdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const QUOTES = ['Show up before the feeling does.', 'Small steps still count as moving.', 'The quiet work is the real work.']
const SUBJECTS = ['runner on a mountain ridge at dawn', 'empty city crosswalk at night', 'fog rolling over a still lake']
const CLIP = { title: 'The honest hour', hook: 'Most people quit too early', description: 'A story about lasting longer.' }
let piece = 0
const fake = createServer((req, res) => {
  let body = ''
  req.on('data', (c) => (body += c))
  req.on('end', () => {
    const text = JSON.parse(body).messages.map((m) => m.content).join('\n')  // clip prompts ride the system message
    const out = text.includes('Plan a batch')
      ? { batch_theme: 'discipline', pieces: SUBJECTS.map((s, i) => ({ angle: ['showing up', 'small habits', 'quiet work'][i], visual_subject: s, visual_type: 'video', intensity: 'medium', narration_style: 'calm reflective' })) }
      : text.includes('scan a video transcript')  // clip pass 1: candidate moments
        ? { moments: [{ start: 0.5, end: 9.5, score: 90, reason: 'a story that lands' }] }
        : text.includes('senior short-form video editor')  // clip pass 2: picks + copy
          ? { clips: [{ id: 0, score: 94, hook: CLIP.hook, title: CLIP.title, description: CLIP.description,
                       hashtags: ['#story'], posts: { tiktok: 'pt', instagram: 'pi', youtube: 'py', linkedin: 'pl', facebook: 'pf', x: 'px' } }] }
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

// Fake Groq Whisper: word-level verbose_json over the whole fixture, whatever audio arrives
const WORDS = ['One.', 'Two.', 'Three.', 'Four.', 'Five.', 'Six.', 'Seven.', 'Eight.', 'Nine.', 'Ten.', 'Eleven.', 'Twelve.']
const fakeGroq = createServer((req, res) => {
  req.on('data', () => {})
  req.on('end', () => res.end(JSON.stringify({
    language: 'en',
    segments: [{ start: 0, end: 11.5, text: WORDS.join(' ') }],
    words: WORDS.map((w, i) => ({ word: w, start: i * 0.95, end: i * 0.95 + 0.6 })),
  })))
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
  ACS_PEXELS_URL: pexelsBase, ACS_GROQ_URL: `http://127.0.0.1:${fakeGroq.address().port}` }
delete env.ELECTRON_RENDERER_URL
delete env.ELECTRON_RUN_AS_NODE

async function launch() {
  const app = await electron.launch({ args: ['.', `--user-data-dir=${join(root, 'profile')}`], env })
  const win = await app.firstWindow()
  win.on('pageerror', (e) => console.error('PAGE ERROR:', e))
  win.on('console', (m) => { if (m.type() === 'error') console.error('CONSOLE ERROR:', m.text()) })
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
await win.getByRole('link', { name: 'GitHub' }).waitFor()
const splashLinks = await win.getByRole('link', { name: /Website|LinkedIn|GitHub/ }).count()
assert.equal(splashLinks, 3, 'three developer links on the splash')
await shot(win, '0-splash')
await assertNoHorizontalOverflowOnSplash(win)
await enterApp(win)
await win.getByRole('heading', { name: 'New project' }).waitFor()
await shot(win, '1-create-empty')
await assertNoHorizontalOverflow(win, 'create')

// Settings: keys (encrypted) + a default
await win.keyboard.press('Control+,')
for (const [labelText, value] of [['DeepSeek API key', 'sk-smoke-deepseek'], ['Pexels API key', 'smoke-test-key-123'], ['Groq API key', 'gsk-smoke-groq']]) {
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

// Create → generate (pieces + visuals): walk the Brief → Delivery → Look wizard, then create
await win.keyboard.press('Control+N')
await win.getByLabel('Topic').fill('discipline')
await win.getByLabel('Genre').click()
await win.getByText('Hard Truth — speech edit', { exact: true }).click()
await win.getByRole('button', { name: 'Next' }).click() // Brief -> Delivery
await win.getByLabel('Narration voice').waitFor()
await win.getByRole('button', { name: 'Next' }).click() // Delivery -> Look
await win.getByLabel('Look').waitFor()
await win.keyboard.press('Control+Enter') // Look -> create + generate
await win.getByText(/Writing piece \d of 3|Planning 3 angles/).waitFor({ timeout: 15_000 })
await shot(win, '4-generating')
await win.locator('blockquote').getByText(QUOTES[2]).waitFor({ timeout: 30_000 })
await win.getByRole('button', { name: /Generate again/ }).waitFor()
await shot(win, '5-project-written')
assert.equal(await win.locator('blockquote').count(), 3)
await assertNoHorizontalOverflow(win, 'project')

// Render: swap the fake downloaded bytes for real clips, set narration speed, render all three pieces
const assetsDir = join(root, 'data', 'media', 'assets')
// 14s: longer than any duration the fake Pexels metadata advertises, so the renderer's middle-segment
// seek always lands inside the real file
for (const f of readdirSync(assetsDir).filter((f) => f.endsWith('.mp4'))) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=1080x1920:rate=30:duration=14',
    '-c:v', 'libx264', '-preset', 'ultrafast', join(assetsDir, f)], { timeout: 120_000, encoding: 'utf8' })
  assert.equal(r.status, 0, `fixture clip failed: ${r.stderr}`)
}
await win.keyboard.press('Control+,')
await win.getByRole('heading', { name: 'Narration' }).waitFor()
await win.getByLabel('Voice engine').click()
await win.getByText('Windows voices (offline)', { exact: true }).click() // kokoro (the default) has no model in the throwaway data dir
await win.getByLabel('Speed').fill('1.1')
await win.getByRole('button', { name: 'Save changes' }).click()
await win.getByText('Saved', { exact: true }).waitFor()
await win.getByRole('heading', { name: 'Narration' }).scrollIntoViewIfNeeded()
await shot(win, '5b-settings-narration')
await win.getByRole('button', { name: 'Projects' }).click()
await win.getByText('Discipline').click()
await win.getByRole('button', { name: 'Render', exact: true }).click()
const chips = () => win.locator('button[title^="renders/"]')
try {
  await chips().first().waitFor({ timeout: 240_000 })
  await win.waitForFunction(() => document.querySelectorAll('button[title^="renders/"]').length === 6,
    undefined, { timeout: 240_000 })
} catch (e) {
  await shot(win, 'debug-render-timeout')
  console.error('PAGE TEXT AT TIMEOUT:', await win.evaluate(() => document.body.innerText.slice(0, 2000)))
  throw e
}
await win.getByText(/Video \d\.\ds/).first().waitFor()
await shot(win, '5c-project-rendered')
await assertNoHorizontalOverflow(win, 'project-rendered')

// Preview: native video player with render facts (PRD 40)
await win.getByRole('button', { name: 'Preview' }).first().click()
await win.locator('video').waitFor({ timeout: 15_000 })
try {
  await win.getByText(/MP4 · H\.264 · 1080 × 1920 · \d+ FPS/).waitFor({ timeout: 20_000 })
} catch (e) {
  await shot(win, 'debug-preview')
  console.error('MODAL TEXT:', await win.evaluate(() => document.querySelector('[role="dialog"]')?.innerText ?? 'NO DIALOG'))
  throw e
}
await shot(win, '5d-preview')
await win.keyboard.press('Escape')

// Approve piece 1, then regenerate its narration (PRD 41/43): its render is stale, chips drop to 2
await win.getByRole('button', { name: 'Preview' }).first().click()
await win.getByRole('button', { name: 'Approve', exact: true }).click()
await win.getByText('Approved', { exact: true }).first().waitFor()
await win.getByRole('button', { name: 'Preview' }).first().click()
await win.getByRole('button', { name: 'Narration' }).click()
await win.waitForFunction(() => document.querySelectorAll('button[title^="renders/"]').length === 4,
  undefined, { timeout: 60_000 })
await win.getByRole('button', { name: 'Render', exact: true }).click()
await win.waitForFunction(() => document.querySelectorAll('button[title^="renders/"]').length === 6,
  undefined, { timeout: 240_000 })

// Export the project (PRD 47): every piece lands in exports/<date>/ and shows as Exported
await win.getByRole('button', { name: 'Export', exact: true }).click()
await win.waitForFunction(() => document.querySelectorAll('main').length &&
    [...document.querySelectorAll('main span')].filter((s) => s.textContent === 'Exported').length === 3,
  undefined, { timeout: 120_000 })
await shot(win, '5e-project-exported')

// Queue screen (PRD 46): stage tabs with counts; the Exported bucket lists every piece
await win.getByRole('button', { name: 'Queue' }).click()
await win.getByRole('tab', { name: /Exported 3/ }).click()
await win.getByText('Show up before the feeling does.').first().waitFor()
await win.waitForTimeout(300) // let the tab's 150ms bg transition finish so the shot shows the selected state
await shot(win, '5f-queue')

// Exports screen: the run is listed with its folder
await win.getByRole('button', { name: 'Exports' }).click()
await win.getByText(/exports.*2026-\d\d-\d\d|Discipline/).first().waitFor()
await win.getByRole('button', { name: 'Open folder' }).waitFor()
await shot(win, '5g-exports')
await assertNoHorizontalOverflow(win, 'exports')
await shot(win, '5c-project-rendered')
await assertNoHorizontalOverflow(win, 'project-rendered')

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
assert.equal(await win.locator('button[title^="renders/"]').count(), 6, 'renders survive restart')
await win.getByRole('button', { name: 'Library' }).click()
await win.getByText('Pexels · Video').first().waitFor()
assert.equal(await win.getByText('Pexels · Video').count(), 3, 'assets survive restart')
await shot(win, '7-library-restart')

// Clip from video (Milestone 7 Phase B): local 12s fixture through fake Groq + the fake DeepSeek's clip passes
const talk = join(root, 'talk.mp4')
{
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=12',
    '-f', 'lavfi', '-i', 'sine=duration=12', '-shortest', talk], { timeout: 120_000, encoding: 'utf8' })
  assert.equal(r.status, 0, `clip fixture failed: ${r.stderr}`)
}
await win.keyboard.press('Control+N')
const chooseCreate = (legend, option) =>
  win.locator('fieldset').filter({ hasText: legend }).getByText(option, { exact: true }).click()
await chooseCreate('What do you want to make?', 'Clip from video')
await win.getByLabel('Video', { exact: true }).fill(talk)
await win.getByText('Advanced').click()
await win.getByLabel('Shortest (s)').fill('5')
await win.getByLabel('Longest (s)').fill('10')
await shot(win, '8-clip-create')
await win.keyboard.press('Control+Enter')
await win.waitForTimeout(3000)
await shot(win, 'debug-after-submit')
try {
  await win.getByText(CLIP.title).waitFor({ timeout: 240_000 })
} catch (e) {
  await shot(win, 'debug-clip-job')
  console.error('PAGE TEXT AT TIMEOUT:', await win.evaluate(() => document.body.innerText.slice(0, 2000)))
  throw e
}
await shot(win, '8b-clip-project')
await assertNoHorizontalOverflow(win, 'clip-project')
await win.getByRole('button', { name: 'Preview', exact: true }).click()
await win.locator('[role="dialog"] video').waitFor({ timeout: 15_000 })
await win.getByText(CLIP.description).waitFor()
await win.getByText('Post copy per platform').click()
await win.getByText('pt', { exact: true }).waitFor()
await shot(win, '8c-clip-preview')
await win.keyboard.press('Escape')
await win.getByRole('button', { name: 'Approve' }).click()
await win.getByText('Approved', { exact: true }).waitFor()
await win.getByRole('button', { name: 'Export', exact: true }).click()
await win.getByText('Exported', { exact: true }).waitFor({ timeout: 120_000 })
await shot(win, '8d-clip-exported')

await win.keyboard.press('Control+N')
await win.keyboard.press('Control+Enter') // Brief -> Delivery, where the quantity lives
await win.getByRole('radio', { name: '3', exact: true }).waitFor()
assert.equal(await win.getByRole('radio', { name: '3', exact: true }).isChecked(), true, 'settings survive restart')
await app.close()
fake.close()
fakeGroq.close()
fakePexels.close()

console.log(`smoke ok, screenshots in ${out}`)
