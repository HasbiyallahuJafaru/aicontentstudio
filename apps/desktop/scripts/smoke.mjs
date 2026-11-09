// End-to-end check of the real app (build first: npm run build). Uses a throwaway data + profile folder and local
// fake OpenRouter (chat + transcription) + Pexels servers (no paid calls). Screenshots go to SMOKE_OUT (default: <tmp>/acs-smoke). Exit 1 on failure.
import { _electron as electron } from 'playwright-core'
import { createServer } from 'node:http'
import { mkdtempSync, readFileSync, readdirSync, mkdirSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const QUOTES = ['Show up before the feeling does.', 'Small steps still count as moving.', 'The quiet work is the real work.']
const SUBJECTS = ['runner on a mountain ridge at dawn', 'empty city crosswalk at night', 'fog rolling over a still lake']
const CLIP = { title: 'The honest hour', hook: 'Most people quit too early', description: 'A story about lasting longer.' }
let piece = 0
// Fake Whisper: word-level verbose_json over the whole fixture, whatever audio arrives
const WORDS = ['One.', 'Two.', 'Three.', 'Four.', 'Five.', 'Six.', 'Seven.', 'Eight.', 'Nine.', 'Ten.', 'Eleven.', 'Twelve.']
const transcription = JSON.stringify({
  language: 'en',
  segments: [{ start: 0, end: 11.5, text: WORDS.join(' ') }],
  words: WORDS.map((w, i) => ({ word: w, start: i * 0.95, end: i * 0.95 + 0.6 })),
})
// Fake Gemini TTS: 3 s of 24 kHz 16-bit mono PCM (a quiet tone), the only format the real one returns
const speech = Buffer.alloc(24000 * 2 * 3)
for (let i = 0; i < 24000 * 3; i++) speech.writeInt16LE(Math.round(4000 * Math.sin(2 * Math.PI * 220 * i / 24000)), i * 2)
// Fake OpenRouter: one base URL, routed by path like the real one (chat, transcription, speech)
const fake = createServer((req, res) => {
  if (req.url.endsWith('/audio/speech')) {
    req.on('data', () => {})
    req.on('end', () => { res.setHeader('Content-Type', 'audio/pcm;rate=24000;channels=1'); res.end(speech) })
    return
  }
  if (req.url.endsWith('/audio/transcriptions')) {
    req.on('data', () => {})
    req.on('end', () => res.end(transcription))
    return
  }
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
          : text.includes('Write these')  // batch writing: one request returns a group of pieces
            ? { pieces: Array.from({ length: Number(text.match(/exactly (\d+) item/)[1]) }, makePiece) }
            : makePiece()
    setTimeout(() => res.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify(out) } }] })), 400)
  })
}).listen(0)

function makePiece() {
  return {
              quote: { text: QUOTES[piece % 3], author: 'Seneca' },  // real-quote genres refuse an authorless line (content._signed)
              narration: { text: `Nobody sees the early hours. ${QUOTES[piece++ % 3]} Keep going anyway.`, delivery: 'calm_reflective' },
              visual: { preferred_type: 'video', search_query: 'runner mountain ridge sunrise', secondary_query: 'trail runner dawn fog', mood: 'quiet determination' },
              design: { text_density: 'low', animation: 'slow', composition: 'editorial' },
              metadata: { title: 'Before the feeling', description: 'A short reflection on discipline and showing up.', caption: 'Start before you feel ready.',
                hashtags: ['#discipline', '#mindset', '#habits'], keywords: ['discipline', 'habits', 'consistency'], alt_text: 'A lone runner on a ridge at sunrise.' },
  }
}

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

// "Download and render" downloads and renders in one job, so the fake footage must be a real video from the start:
// 14s, longer than any duration the fake Pexels metadata advertises, so the renderer's middle-segment seek always
// lands inside the file
const fixtureClip = join(mkdtempSync(join(tmpdir(), 'acs-clip-')), 'clip.mp4')
{
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=1080x1920:rate=30:duration=14',
    '-c:v', 'libx264', '-preset', 'ultrafast', fixtureClip], { timeout: 120_000, encoding: 'utf8' })
  assert.equal(r.status, 0, `fixture clip failed: ${r.stderr}`)
}
const fixtureBytes = readFileSync(fixtureClip)
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
    res.end(fixtureBytes)
  } else {
    res.statusCode = 404
    res.end()
  }
}).listen(0)
pexelsBase = `http://127.0.0.1:${fakePexels.address().port}`

// SMOKE_DATA pins the data folder so a debug run's renders survive for inspection; default is throwaway
const root = process.env.SMOKE_DATA || mkdtempSync(join(tmpdir(), 'acs-'))
const out = process.env.SMOKE_OUT || join(tmpdir(), 'acs-smoke')
mkdirSync(out, { recursive: true })
const env = { ...process.env, ACS_DATA_DIR: join(root, 'data'), ACS_OPENROUTER_URL: `http://127.0.0.1:${fake.address().port}`,
  ACS_PEXELS_URL: pexelsBase, ACS_MIN_CLIP: '1' }  // real clips run at least a minute; the fixture is 12 s
delete env.ELECTRON_RENDERER_URL
delete env.ELECTRON_RUN_AS_NODE

async function launch() {
  const app = await electron.launch({ args: ['.', `--user-data-dir=${join(root, 'profile')}`], env })
  const win = await app.firstWindow()
  win.on('pageerror', (e) => console.error('PAGE ERROR:', e))
  win.on('console', (m) => { if (m.type() === 'error') console.error('CONSOLE ERROR:', m.text()) })
  await win.setViewportSize({ width: 1440, height: 900 })
  await win.emulateMedia({ reducedMotion: 'reduce' })
  // the creator card pops up after finished jobs (twice a day); a pop-up mid-run would swallow the next click
  await win.evaluate(() => localStorage.setItem('acs.creatorCard', JSON.stringify({ day: new Date().toLocaleDateString('sv'), count: 99 })))
  await win.getByRole('button', { name: "Let's create content" }).waitFor({ timeout: 30_000 })
  return { app, win }
}

async function enterApp(win) {
  await win.getByRole('button', { name: "Let's create content" }).click()
  // the status is a dot now; its words live in a screen-reader span and a hover tooltip, so match the region
  await win.getByRole('status').filter({ hasText: 'Engine ready' }).waitFor({ timeout: 30_000 })
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
// the fan of bundled design-engine renders, every image decoded (a broken import would show empty cards)
await win.waitForFunction(() => {
  const imgs = [...document.querySelectorAll('.bounce-cards__card img')]
  return imgs.length === 5 && imgs.every((i) => i.complete && i.naturalWidth > 0)
}, undefined, { timeout: 15_000 })
await shot(win, '0-splash')
await assertNoHorizontalOverflowOnSplash(win)
// first run: no keys yet, so the setup screens come between the splash and the studio, one key per screen
await win.getByRole('button', { name: "Let's create content" }).click()
await win.getByRole('heading', { name: 'Connect the AI' }).waitFor({ timeout: 30_000 })
await win.getByText('Step 1 of 5').waitFor()
await shot(win, '0c-setup-openrouter')
for (const [label, value, nextHeading] of [['OpenRouter key', 'sk-or-smoke', 'Add stock footage'],
  ['Pexels key', 'smoke-test-key-123', 'More photos']]) {
  await win.getByLabel(label).fill(value)
  await win.getByRole('button', { name: 'Save and continue' }).click()
  await win.getByRole('heading', { name: nextHeading }).waitFor()
}
await win.getByRole('button', { name: 'Skip for now' }).click()  // Unsplash is optional
await win.getByRole('heading', { name: 'Post to your socials' }).waitFor()
await win.getByLabel('Zernio API key').waitFor()  // the connection check loads after the heading
assert.equal(await win.getByLabel('Zernio API key').count(), 1, 'Zernio is set up with a pasted key')
assert.equal(await win.getByRole('button', { name: /Open zernio\.com/ }).count(), 1, 'setup links to Zernio sign-up')
await shot(win, '0d-setup-posting')
await win.getByRole('button', { name: 'Skip for now' }).click()
await win.getByRole('heading', { name: "You're set up" }).waitFor()
await shot(win, '0e-setup-done')
await win.getByRole('button', { name: 'Start creating' }).click()
await win.getByRole('status').filter({ hasText: 'Engine ready' }).waitFor({ timeout: 30_000 })
await win.getByRole('heading', { name: /^(Good (morning|afternoon|evening)|Working late),/ }).waitFor() // the splash opens the Dashboard
assert.equal(await win.locator('canvas').count(), 0, 'the white room has no background canvases')
// the rail's hover label must paint over the page, not under it (owner report 2026-11-08). Motion on: the rail's
// entrance animation keeps a transform, which gives the rail its own layer, and that is when the bug shows.
{
  await win.emulateMedia({ reducedMotion: 'no-preference' })
  await win.waitForTimeout(1000)
  const item = win.locator('nav[aria-label="Main"] button[aria-label="Library"]')
  await item.hover()
  await win.waitForTimeout(400)
  const onTop = await item.evaluate((btn) => {
    const tip = btn.querySelector('span[aria-hidden]')
    const r = tip.getBoundingClientRect()
    tip.style.pointerEvents = 'auto'  // hit-testing skips pointer-events: none, which the label uses
    const hit = document.elementFromPoint(r.right - 4, r.top + r.height / 2)
    tip.style.pointerEvents = ''
    return hit === tip || tip.contains(hit)
  })
  assert.ok(onTop, 'rail label is drawn above the page')
  await win.mouse.move(700, 450)
  await win.emulateMedia({ reducedMotion: 'reduce' })
}
await win.keyboard.press('Control+N')
await win.getByRole('heading', { name: 'New project' }).waitFor()
assert.equal(await win.getByRole('listbox').count(), 0, 'no suggestion list pops open on arrival')
await win.getByRole('heading', { name: 'What are you making?' }).waitFor()
// the chooser's three photos ship inside the app (assets/create), every one decoded
await win.waitForFunction(() => {
  const imgs = [...document.querySelectorAll('button img')]
  return imgs.length === 3 && imgs.every((i) => i.complete && i.naturalWidth > 0)
}, undefined, { timeout: 15_000 })
await shot(win, '1-create-empty')
await assertNoHorizontalOverflow(win, 'create')

// Quote images from the user's own lines: the preview sets those exact lines in the chosen design
await win.getByRole('button', { name: /^Quote images/ }).click()
await win.getByRole('heading', { name: 'Quote images' }).waitFor()
await win.getByText('I have my own', { exact: true }).click()
await win.getByLabel('Your quotes').fill(['Your comfort zone will kill you.', 'Life has no script. Live it. — Anonymous'].join(String.fromCharCode(10)))
// bulk: a spreadsheet export with a header, quote + author columns, a skipped (too long) row
const csvPath = join(root, 'quotes.csv')
writeFileSync(csvPath, ['quote,author', '"Rest, then go again.",Seneca', 'Begin anyway.,', `${'x'.repeat(200)},Nobody`].join('\n'))
await win.getByLabel('Import a CSV of quotes').setInputFiles(csvPath)
await win.getByRole('status').filter({ hasText: 'Added 2 quotes from quotes.csv, 1 with an author.' }).waitFor()
await win.getByText('Skipped 1: row 4 (over 180 characters).').waitFor()
await win.getByText('4 quotes', { exact: true }).waitFor()
await win.getByRole('button', { name: 'Next' }).click() // Quotes -> Design
try {
  await win.getByRole('group', { name: 'Image design' }).waitFor()
} catch (e) {
  await shot(win, 'debug-quote-design')
  console.error('PAGE TEXT:', await win.evaluate(() => document.body.innerText.slice(0, 1500)))
  throw e
}
await win.getByRole('group', { name: 'Image design' }).getByText('Noir poster', { exact: true }).click()
await win.waitForFunction(() => document.querySelectorAll('section[aria-label="Preview"] img').length >= 2,
  undefined, { timeout: 30_000 })
await win.getByText('Your quotes, set exactly as they will render.', { exact: false }).waitFor()
await win.getByText('001 · Noir poster', { exact: true }).waitFor({ timeout: 30_000 }) // the pick reaches the preview
await win.locator('section[aria-label="Preview"] [aria-busy="false"]').waitFor()
await win.locator('button[type="submit"]').waitFor() // the keys went in at setup, so it creates for real
assert.equal(await win.getByRole('button', { name: 'Save as draft' }).count(), 0, 'keys from setup are live')
await shot(win, '1b-quote-images')
await assertNoHorizontalOverflow(win, 'quote-images')
await win.getByRole('button', { name: 'All formats' }).click()
await win.getByRole('heading', { name: 'What are you making?' }).waitFor()

// Settings: keys (encrypted) + a plain-language choice
await win.keyboard.press('Control+,')
for (const [labelText, value] of [['OpenRouter API key', 'sk-or-smoke'], ['Pexels API key', 'smoke-test-key-123']]) {
  await win.getByLabel(labelText).fill(value)
  await win.getByLabel(labelText).press('Enter')
}
await win.getByText('Saved and encrypted on this computer').nth(1).waitFor()
await win.getByLabel('Quality').click()
await win.getByText('Standard · smaller files', { exact: true }).click()
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
await win.getByRole('button', { name: /^Narrated videos/ }).click()
await win.getByLabel('Topic').fill('discipline')
await win.getByLabel('Genre').click()
await win.getByText('Hard Truth — speech edit', { exact: true }).click()
await win.getByRole('group', { name: 'How many' }).getByText('3', { exact: true }).click()
await win.getByRole('button', { name: 'Next' }).click() // Brief -> Delivery
await win.getByLabel('Narration voice').waitFor()
await win.getByRole('button', { name: 'Next' }).click() // Delivery -> Look
await win.getByLabel('Look').waitFor()
await win.getByText('Also a 4:5 picture', { exact: true }).click() // video + designed image per piece
// subtitles default on (owner decision 2026-11-08); burning them into six full-size renders pushes this walk past its
// render timeouts, and the burn itself is covered by test_render's subtitle renders, so the smoke turns them off
await win.getByRole('group', { name: 'Subtitles' }).getByText('Off', { exact: true }).click()
await win.keyboard.press('Control+Enter') // Look -> create + generate
await win.getByText(/Writing pieces? [\d-]+ of 3|Planning 3 angles/).first().waitFor({ timeout: 15_000 })  // header + step log both show it
await shot(win, '4-generating')
await win.locator('blockquote').getByText(QUOTES[2]).waitFor({ timeout: 30_000 })
await win.getByRole('button', { name: /Generate again/ }).waitFor()
await shot(win, '5-project-written')
assert.equal(await win.locator('blockquote').count(), 3)
await assertNoHorizontalOverflow(win, 'project')

// Footage review: nothing full-size downloads until the picks are confirmed (owner decision 2026-11-07)
const assetsDir = join(root, 'data', 'media', 'assets')
const fullFiles = () => { try { return readdirSync(assetsDir).filter((f) => f.endsWith('.mp4')).length } catch { return 0 } }
await win.getByRole('heading', { name: 'Choose the footage' }).waitFor()
assert.equal(fullFiles(), 0, 'no footage downloaded before the user confirms')
await shot(win, '5a-footage-review')
// one button under the shots: download exactly the picks, then render every piece
await win.getByRole('button', { name: 'Download and render' }).click()
await win.getByRole('heading', { name: 'Choose the footage' }).waitFor({ state: 'detached', timeout: 60_000 })
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
assert.ok(fullFiles() > 0, 'confirmed footage is downloaded')
await win.getByText(/Video \d\.\ds/).first().waitFor()
await shot(win, '5c-project-rendered')
await assertNoHorizontalOverflow(win, 'project-rendered')
// a rendered piece can be posted; without Zernio set up the dialog points to Settings
await win.getByRole('button', { name: 'Post', exact: true }).first().click()
await win.getByText('Set up posting once', { exact: true }).waitFor()
await shot(win, '5c2-post-piece')
await win.keyboard.press('Escape')
await win.locator('[role="dialog"]').waitFor({ state: 'detached' })

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

// No approve step (owner 2026-11-08); "Schedule all" is offered once pieces are rendered
assert.equal(await win.getByRole('button', { name: 'Approve', exact: true }).count(), 0, 'no approve button')
await win.getByRole('button', { name: 'Schedule all' }).click()
await win.getByText('Set up posting once', { exact: true }).waitFor()
await shot(win, '5e-schedule-all-setup')
await win.keyboard.press('Escape')
await win.locator('[role="dialog"]').first().waitFor({ state: 'detached' }).catch(() => win.keyboard.press('Escape'))
// Regenerate piece 1's narration (PRD 41/43): its render is stale, chips drop to 2
await win.getByRole('button', { name: 'Preview' }).first().click()
await win.getByRole('button', { name: 'Narration' }).click()
await win.waitForFunction(() => document.querySelectorAll('button[title^="renders/"]').length === 4,
  undefined, { timeout: 60_000 })
await win.getByRole('button', { name: 'Render', exact: true }).click()
await win.waitForFunction(() => document.querySelectorAll('button[title^="renders/"]').length === 6,
  undefined, { timeout: 240_000 })

// Export the project (PRD 47): every piece lands in exports/<date>/ and shows as Exported
// Export stays disabled until the whole re-render job finishes, not just piece 1's chips: wait for the job
await win.getByRole('button', { name: 'Export', exact: true }).click({ timeout: 240_000 })
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
// each piece now cuts between several shots, so an asset's usage count is no longer always 1
await win.getByText(/Used \d+ times?/).first().waitFor()
assert.ok(await win.locator('main span[title^="#"]').count() >= 3, 'dominant color swatches shown')
await shot(win, '6-library')
// the full-screen carousel: a tile opens it, arrows step through, Escape closes
await win.getByRole('button', { name: 'Pexels · Video' }).first().click()
await win.getByRole('dialog').waitFor()
await win.getByRole('button', { name: 'Next' }).waitFor()
await shot(win, '6a-library-carousel')
await win.keyboard.press('ArrowRight')
await win.keyboard.press('Escape')
await win.getByRole('dialog').waitFor({ state: 'detached' })
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
// the hero's crowd holds the project's real covers (clickable) and samples fill the rest
await win.getByRole('button', { name: 'Open Discipline' }).first().waitFor()
await win.waitForTimeout(1200) // the crowd's rise-in finishes
await shot(win, '6b-dashboard-data')
// the crowd never climbs into the buttons, at the default size or on a wide window (owner bug 2026-11-08)
for (const [w, h] of [[1440, 900], [1920, 1020], [1024, 680]]) {
  await win.setViewportSize({ width: w, height: h })
  await win.waitForTimeout(400)
  const gap = await win.evaluate(() => {
    const buttons = [...document.querySelectorAll('section button')].find((b) => b.textContent.includes('New project'))
    const tiles = [...document.querySelectorAll('[class*="container-type"] > div')]
    const top = Math.min(...tiles.map((t) => t.getBoundingClientRect().top))
    return top - buttons.getBoundingClientRect().bottom
  })
  assert.ok(gap > 8, `dashboard crowd overlaps the buttons at ${w}x${h} (gap ${gap}px)`)
  if (w === 1920) await shot(win, '6c-dashboard-wide')
}
await win.setViewportSize({ width: 1440, height: 900 })
await win.getByRole('button', { name: 'Pick up Discipline' }).click()
await win.locator('blockquote').getByText(QUOTES[0]).waitFor()
assert.equal(await win.locator('button[title^="renders/"]').count(), 6, 'renders survive restart')
await win.getByRole('button', { name: 'Library' }).click()
await win.getByText('Pexels · Video').first().waitFor()
assert.equal(await win.getByText('Pexels · Video').count(), 3, 'assets survive restart')
await shot(win, '7-library-restart')

// Clip from video (Milestone 7 Phase B): local 12s fixture through the fake OpenRouter's transcription + clip passes
const talk = join(root, 'talk.mp4')
{
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=12',
    '-f', 'lavfi', '-i', 'sine=duration=12', '-shortest', talk], { timeout: 120_000, encoding: 'utf8' })
  assert.equal(r.status, 0, `clip fixture failed: ${r.stderr}`)
}
await win.keyboard.press('Control+N')
await win.getByRole('button', { name: /^Clips from a video/ }).click()
assert.equal(await win.getByRole('button', { name: 'Choose a file' }).count(), 1, 'a video on this computer can be chosen')
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
// post copy: one network at a time behind tabs, each with its own copy and a copy button
await win.getByRole('tab', { name: 'TikTok' }).waitFor()
await win.getByText('pt', { exact: true }).waitFor()
await win.getByRole('tab', { name: 'Instagram' }).click()
await win.getByText('pi', { exact: true }).waitFor()
assert.equal(await win.getByRole('button', { name: 'Copy', exact: true }).count(), 1, 'post copy can be copied')
await win.waitForTimeout(300) // let the chip colour settle
await shot(win, '8c-clip-preview')
await win.keyboard.press('Escape')
assert.equal(await win.getByRole('button', { name: 'Approve' }).count(), 0, 'clips post without an approve step')
assert.equal(await win.getByRole('button', { name: 'Schedule all' }).count(), 1, 'every clip can be scheduled at once')
// publishing goes through Zernio; before it is set up the dialog points to Settings
await win.getByRole('button', { name: 'Preview', exact: true }).click()
await win.locator('[role="dialog"]').getByRole('button', { name: 'Post', exact: true }).click()
await win.getByText('Set up posting once', { exact: true }).waitFor()
assert.equal(await win.getByRole('button', { name: 'Open Settings' }).count(), 1, 'publish dialog links to Settings')
await win.waitForTimeout(300)
await shot(win, '8e-publish-setup')
await win.keyboard.press('Escape')
await win.locator('[role="dialog"]').first().waitFor({ state: 'detached' }).catch(() => win.keyboard.press('Escape'))
await win.getByRole('button', { name: 'Export', exact: true }).click()
await win.getByText('Exported', { exact: true }).waitFor({ timeout: 120_000 })
await shot(win, '8d-clip-exported')

// The creator card (React Bits Lanyard) renders its 3D canvas and closes on Escape
await win.evaluate(() => window.dispatchEvent(new Event('creator-card:open')))
await win.locator('canvas.lanyard-canvas').waitFor({ timeout: 30_000 })
await win.waitForTimeout(800)
await shot(win, '9-creator-card')
await win.keyboard.press('Escape')
await win.locator('canvas.lanyard-canvas').waitFor({ state: 'detached' })

// Settings survive the restart; then Clear all content wipes every project and file, keys and settings stay
await win.keyboard.press('Control+,')
assert.match(await win.getByLabel('Quality').textContent(), /Standard/, 'settings survive restart')
await win.getByRole('heading', { name: 'Posting' }).scrollIntoViewIfNeeded()
await shot(win, '9a-settings-posting')
win.once('dialog', (d) => d.accept())
await win.getByRole('button', { name: 'Clear all content' }).click()
await win.getByText(/Cleared\. .* freed\./).waitFor({ timeout: 60_000 })
await shot(win, '9-settings-cleared')
await assertNoHorizontalOverflow(win, 'settings')
await win.getByRole('button', { name: 'Projects' }).click()
await win.getByText('No projects yet').waitFor()
await app.close()
fake.close()
fakePexels.close()

console.log(`smoke ok, screenshots in ${out}`)
