import '@fontsource-variable/geist'
import './style.css'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { injectIcons } from './icons'

// Downloads go through a Cloudflare Turnstile check: the widget's single-use token is handed to the download Worker
// (apps/download-worker), which verifies it and streams the installer from a private bucket. There is no public file.
const GATE = import.meta.env.VITE_DOWNLOAD_GATE || 'https://ytclipper-download.jafaruhasbiyallahu-cc1.workers.dev/download'
// the widget's public site key; Cloudflare's always-pass test key in local dev only
const SITEKEY = import.meta.env.VITE_TURNSTILE_SITEKEY || (import.meta.env.DEV ? '1x00000000000000000000AA' : '')
const urls = (g: Record<string, unknown>) => Object.keys(g).sort().map((k) => g[k] as string)
const RENDERS = urls(import.meta.glob('./assets/renders/*.webp', { eager: true, import: 'default' }))
const FOOTAGE = urls(import.meta.glob('./assets/footage/clip-*.webp', { eager: true, import: 'default' }))
const ART = urls(import.meta.glob('./assets/footage/{clips,images,videos}.webp', { eager: true, import: 'default' }))
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
const $ = <T extends Element = HTMLElement>(s: string, root: ParentNode = document) => root.querySelector<T>(s)!
const $$ = <T extends Element = HTMLElement>(s: string, root: ParentNode = document) => [...root.querySelectorAll<T>(s)]
const img = (src: string, cls = '') => `<img src="${src}" alt="" loading="lazy" decoding="async"${cls ? ` class="${cls}"` : ''} />`

injectIcons()
gsap.registerPlugin(ScrollTrigger)

// smooth scroll drives one clock for everything; its velocity feeds the hero line and the endless rows
let velocity = 0
let lenis: Lenis | undefined
if (!reduce) {
  lenis = new Lenis({ lerp: 0.1, anchors: { offset: -80 } })
  lenis.on('scroll', (e: Lenis) => { velocity = e.velocity; ScrollTrigger.update() })
  gsap.ticker.add((t) => lenis!.raf(t * 1000))
  gsap.ticker.lagSmoothing(0)
}

// the hero line loads after first paint, so the headline and button never wait on three.js
const canvas = $<HTMLCanvasElement>('.hero-canvas')
let hero: { push(v: number): void } | undefined
const startHero = () => import('./hero').then(({ mountHero }) => { hero = mountHero(canvas, RENDERS, FOOTAGE) })
if ('requestIdleCallback' in window) requestIdleCallback(startHero, { timeout: 500 }); else setTimeout(startHero, 200)
gsap.ticker.add(() => hero?.push(velocity))

// nav: a floating pill past the top, tucked away while reading down, back on any scroll up
const nav = $('[data-nav]')
new IntersectionObserver(([e]) => nav.classList.toggle('scrolled', !e.isIntersecting)).observe($('.top-sentinel'))
let lastY = scrollY
addEventListener('scroll', () => {
  const y = scrollY
  nav.classList.toggle('away', y > lastY && y > 600)
  lastY = y
}, { passive: true })

// reveal on entry: each block rises in once, the first time it is seen
const reveal = new IntersectionObserver((entries) => entries.forEach((e) => {
  if (!e.isIntersecting) return
  e.target.classList.add('in')
  reveal.unobserve(e.target)
}), { rootMargin: '0px 0px -8% 0px' })
$$('[data-reveal]').forEach((el) => (reduce ? el.classList.add('in') : reveal.observe(el)))

/** An endless row: the children are repeated until the track is twice the screen, then it slides by half its width
 *  forever. Scroll velocity speeds it up (in the row's own direction) and leans it. */
function endless(track: HTMLElement, speed: number, lean = 0) {
  const base = track.innerHTML
  while (track.scrollWidth < innerWidth * 2 + 200) track.insertAdjacentHTML('beforeend', base)
  track.insertAdjacentHTML('beforeend', track.innerHTML)
  track.querySelectorAll('img').forEach((im, i) => i && im.setAttribute('aria-hidden', 'true'))
  if (reduce) return
  let x = 0, skew = 0
  const setX = gsap.quickSetter(track, 'x', 'px')
  const setSkew = gsap.quickSetter(track, 'skewX', 'deg')
  gsap.ticker.add((_, dt) => {
    const half = track.scrollWidth / 2
    x -= (speed + Math.abs(velocity) * 0.9 * Math.sign(speed || 1)) * (dt / 16.7)
    if (x <= -half) x += half
    if (x > 0) x -= half
    setX(x)
    if (lean) { skew += (gsap.utils.clamp(-8, 8, -velocity * lean) - skew) * 0.1; setSkew(skew) }
  })
}

endless($('[data-band]'), 1.1)

// karaoke captions: three words on screen at a time, the spoken one in lime, looping for as long as the page is open
$$('[data-caption]').forEach((el, n) => {
  const words = el.dataset.caption!.split(' ')
  el.innerHTML = words.map((w) => `<span>${w}</span>`).join(' ')
  const spans = $$('span', el)
  if (reduce) { spans.forEach((s) => s.classList.add('on')); return }
  let i = -1
  setTimeout(() => setInterval(() => {
    i = (i + 1) % (words.length + 3)
    const group = Math.floor(Math.min(i, words.length - 1) / 3)
    spans.forEach((s, k) => {
      s.classList.toggle('on', Math.floor(k / 3) === group && k <= i && i < words.length)
      s.classList.toggle('now', k === i)
    })
  }, 330), n * 140)
})

/* ---------------------------------------------------------------------------------------------------------------
   The cut: a pinned black room. The source episode scrolls past the playhead as you scroll; every word it passes is
   heard; the three phrases that stand alone light up lime, and the phones rise with those phrases as captions. */
const PHRASES = $$('[data-phone] [data-caption]').map((el) => el.dataset.caption!)
const FILLER = [
  'so I want to start with something that took me years to understand',
  'and honestly it changed how I think about every single project I take on',
  'when you look at the people you admire you only ever see the result',
  'what you do not see is the hundreds of mornings that looked exactly the same',
  'and that is the part I want to talk about today',
]
const transcript = [FILLER[0], PHRASES[0], FILLER[1], FILLER[2], PHRASES[1], FILLER[3], PHRASES[2], FILLER[4]]
const picks = new Set<number>()
const wordsEl = $('[data-words]')
let count = 0
wordsEl.innerHTML = transcript.map((part) => {
  const isPick = PHRASES.includes(part)
  return part.split(' ').map((w) => { if (isPick) picks.add(count); count++; return `<span>${w}</span>` }).join(' ')
}).join(' ')
const wordSpans = $$('span', wordsEl)
$('[data-frames]').innerHTML = Array.from({ length: 30 }, (_, i) => img(FOOTAGE[(i * 7) % FOOTAGE.length])).join('')
$('[data-wave]').innerHTML = Array.from({ length: Math.ceil(wordsEl.scrollWidth / 6) }, (_, i) => {
  const h = 18 + 70 * Math.abs(Math.sin(i * 0.37) * Math.sin(i * 0.11 + 1) + 0.3 * Math.sin(i * 1.7))
  return `<span style="height:${Math.min(100, h).toFixed(0)}%"></span>`
}).join('')

const track = $('[data-track]')
const head = $('.source-head')
const frameImgs = $$('img', $('[data-frames]'))
const bars = $$('span', $('[data-wave]'))
const stepEl = $('[data-cut-step]')
const timecode = $('[data-timecode]')
const phones = $$('[data-phone]')
const STEPS = ['It listens to every word.', 'It finds the moments that stand alone.', 'It cuts them vertical, with captions.', 'Ready for Shorts, Reels and TikTok.']

/** light up whatever has passed the playhead; picked words, and the frames and bars above them, turn lime */
function hearUpTo(px: number) {
  const pickRanges: [number, number][] = []
  wordSpans.forEach((s, i) => {
    const r = s.getBoundingClientRect()
    const heard = r.left < px
    s.classList.toggle('heard', heard)
    s.classList.toggle('pick', heard && picks.has(i))
    if (heard && picks.has(i)) pickRanges.push([r.left, r.right])
  })
  const inPick = (a: number, b: number) => pickRanges.some(([l, r]) => b > l && a < r)
  bars.forEach((b) => { const r = b.getBoundingClientRect(); b.classList.toggle('lit', r.left < px && inPick(r.left, r.right)) })
  frameImgs.forEach((f) => { const r = f.getBoundingClientRect(); f.classList.toggle('pick', r.left < px && inPick(r.left + r.width * 0.3, r.right - r.width * 0.3)) })
}

if (!reduce) {
  gsap.from('.cut-panel', { scale: 0.86, borderRadius: 64, ease: 'none', scrollTrigger: { trigger: '.cut', start: 'top bottom', end: 'top top', scrub: true } })
  gsap.set(phones, { yPercent: 120, rotate: (i) => (i - 1) * 6, opacity: 0 })
  const distance = () => track.scrollWidth - track.parentElement!.clientWidth * 0.5
  const tl = gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: {
      trigger: '.cut', start: 'top top', end: () => `+=${innerHeight * 3.2}`, pin: '.cut-pin', scrub: 0.6,
      invalidateOnRefresh: true,
      onUpdate: (st) => {
        const p = st.progress
        stepEl.textContent = STEPS[Math.min(3, Math.floor(p * 4.2))]
        const secs = Math.floor(p * 3720)
        timecode.textContent = [secs / 3600, (secs / 60) % 60, secs % 60].map((v) => String(Math.floor(v)).padStart(2, '0')).join(':')
      },
    },
    // the scrubbed timeline lags the scroll on purpose, so the playhead reads positions on the timeline's own beat
    onUpdate: () => hearUpTo(head.getBoundingClientRect().left),
  })
  tl.to(track, { x: () => -distance(), duration: 1 }, 0)
  phones.forEach((ph, i) => tl.to(ph, { yPercent: 0, rotate: (i - 1) * 3, opacity: 1, duration: 0.16, ease: 'power3.out' }, 0.5 + i * 0.13))
  tl.to(phones, { y: (i) => (i === 1 ? -18 : 0), rotate: 0, duration: 0.12, ease: 'power2.out' }, 0.88)
} else {
  wordSpans.forEach((s, i) => s.classList.add('heard', ...(picks.has(i) ? ['pick'] : [])))
}

/* --- the bento's live cells ------------------------------------------------------------------------------------- */
// quote deck: three renders fanned, the back one dealt to the front every couple of seconds
const deck = $('[data-deck]')
deck.innerHTML = RENDERS.map((s) => img(s)).join('')
const deckImgs = $$('img', deck)
const FAN = [{ x: -50, y: -6, r: 0, z: 3, o: 1 }, { x: -96, y: 6, r: -10, z: 2, o: 1 }, { x: -4, y: 6, r: 10, z: 1, o: 1 }]
let top = 0
function dealDeck() {
  deckImgs.forEach((im, i) => {
    const slot = (i - top + deckImgs.length) % deckImgs.length
    const f = FAN[slot] ?? { x: -50, y: 30, r: 0, z: 0, o: 0 }
    im.style.transform = `translateX(${f.x}%) translateY(${f.y}px) rotate(${f.r}deg) scale(${slot === 0 ? 1 : 0.92})`
    im.style.zIndex = String(f.z)
    im.style.opacity = String(f.o)
  })
}
dealDeck()
if (!reduce) setInterval(() => { top = (top + 1) % deckImgs.length; dealDeck() }, 2200)

// narration: an equaliser that never sits still
const eq = $('[data-eq]')
eq.innerHTML = '<span></span>'.repeat(32)
if (!reduce) gsap.to($$('span', eq), { scaleY: 'random(0.15, 1)', duration: 'random(0.25, 0.6)', ease: 'sine.inOut', repeat: -1, yoyo: true, repeatRefresh: true, stagger: { each: 0.03, from: 'center' } })

// schedule: a week of posts rolling past
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const week = $('[data-week]')
week.innerHTML = DAYS.map((d, i) => `<div class="day">${d} ${String(9 + ((i * 3) % 9)).padStart(2, '0')}:00${img(RENDERS[(i + 2) % RENDERS.length])}</div>`).join('')
endless(week, 0.5)

/* --- tour: each slide eases back as the next one lands on it (opaque throughout, so the stack never shows through) */
const slides = $$('[data-slide]')
if (!reduce) slides.slice(0, -1).forEach((slide, i) => {
  gsap.to(slide, {
    scale: 0.95, y: -12, ease: 'none',
    scrollTrigger: { trigger: slides[i + 1], start: 'top bottom', end: 'top 96px', scrub: true },
  })
})

/* --- gallery: two endless rows going opposite ways, real output only ------------------------------------------ */
const [rowA, rowB] = $$('.row-track')
rowA.innerHTML = RENDERS.map((s) => img(s)).join('')
rowB.innerHTML = [...ART, ...RENDERS.slice().reverse()].map((s, i) => img(s, i < ART.length ? 'wide' : '')).join('')
endless(rowA, 0.9, 0.35)
endless(rowB, -0.9, 0.35)

/* --- statement: words fill in with the scroll; the last two land on lime --------------------------------------- */
const fill = $('[data-fill]')
const fillWords = fill.textContent!.trim().split(' ')
fill.setAttribute('aria-label', fill.textContent!.trim())
fill.innerHTML = fillWords.map((w) => `<span class="w" aria-hidden="true">${w}</span>`).join(' ')
const ws = $$('.w', fill)
ws.slice(4, 6).forEach((w) => w.dataset.hi = '1')
const paintFill = (p: number) => ws.forEach((w, i) => {
  const on = i < p * (ws.length + 1)
  w.classList.toggle('on', on)
  w.classList.toggle('hi', on && !!w.dataset.hi)
})
if (reduce) paintFill(1)
else ScrollTrigger.create({ trigger: fill, start: 'top 80%', end: 'bottom 40%', scrub: true, onUpdate: (st) => paintFill(st.progress) })

/* --- the ring above the last button ---------------------------------------------------------------------------- */
const ring = $('[data-ring]')
const RING = [...RENDERS, ...FOOTAGE.slice(0, 8)]
ring.innerHTML = RING.map((s) => img(s)).join('')
const placeRing = () => {
  const w = ring.clientWidth
  const radius = (w * 1.12) / (2 * Math.tan(Math.PI / RING.length))
  $$('img', ring).forEach((im, i) => { im.style.transform = `rotateY(${(i * 360) / RING.length}deg) translateZ(${radius}px)` })
  ring.parentElement!.style.perspectiveOrigin = '50% 30%'
  ring.style.translate = `0 0 ${-radius}px`
}
placeRing()
addEventListener('resize', placeRing)

/* --- the footer wordmark: letters lift under the pointer ------------------------------------------------------- */
const mark = $('.wordmark')
mark.innerHTML = [...mark.textContent!].map((c) => (c === ' ' ? ' ' : `<span class="ch">${c}</span>`)).join('')

/* --- cursor and magnetic buttons (fine pointers only) ---------------------------------------------------------- */
if (!reduce && matchMedia('(pointer: fine)').matches) {
  const cursor = $('.cursor')
  const cx = gsap.quickTo(cursor, 'x', { duration: 0.35, ease: 'power3' })
  const cy = gsap.quickTo(cursor, 'y', { duration: 0.35, ease: 'power3' })
  addEventListener('pointermove', (e) => {
    cx(e.clientX); cy(e.clientY)
    const t = e.target as Element
    cursor.classList.toggle('big', !!t.closest('img, canvas, .phone'))
    cursor.classList.toggle('hide', !!t.closest('a, button, summary'))
  }, { passive: true })
  $$('[data-magnetic]').forEach((btn) => {
    const mx = gsap.quickTo(btn, 'x', { duration: 0.6, ease: 'elastic.out(1, 0.4)' })
    const my = gsap.quickTo(btn, 'y', { duration: 0.6, ease: 'elastic.out(1, 0.4)' })
    btn.addEventListener('pointermove', (e) => {
      const r = btn.getBoundingClientRect()
      mx((e.clientX - r.left - r.width / 2) * 0.25); my((e.clientY - r.top - r.height / 2) * 0.35)
    })
    btn.addEventListener('pointerleave', () => { mx(0); my(0) })
  })
}

// images load late and change layout heights; let the pinned scenes re-measure
addEventListener('load', () => ScrollTrigger.refresh())

/* --- the download check: a native dialog holding the Turnstile widget, loaded on first use ---------------------- */
type Turnstile = { render(el: HTMLElement, o: object): string; reset(id?: string): void; remove(id: string): void }
const gate = $<HTMLDialogElement>('[data-gate]')
const gateMsg = $('[data-gate-msg]', gate)
const slot = $('[data-turnstile]', gate)
const HELLO = gateMsg.textContent
let loading: Promise<void> | undefined
let widget: string | undefined
const loadTurnstile = () => (loading ??= new Promise<void>((resolve, reject) => {
  const s = document.createElement('script')
  s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
  s.async = true
  s.onload = () => resolve()
  s.onerror = () => { loading = undefined; reject(new Error('turnstile')) }
  document.head.append(s)
}))

async function openGate() {
  gateMsg.textContent = HELLO
  gate.showModal()
  if (!SITEKEY) { gateMsg.textContent = 'Downloads are being set up. Please try again shortly.'; return }
  try { await loadTurnstile() } catch {
    gateMsg.textContent = "The check couldn't load. Check your connection, or pause an ad blocker for this site, then try again."
    return
  }
  const ts = (window as unknown as { turnstile: Turnstile }).turnstile
  if (widget) ts.remove(widget)
  widget = ts.render(slot, {
    sitekey: SITEKEY, theme: 'auto', action: 'download',
    callback: (token: string) => {
      gateMsg.textContent = 'Thanks. Your download is starting.'
      location.href = `${GATE}?t=${encodeURIComponent(token)}`
      setTimeout(() => gate.close(), 2500)
    },
    'error-callback': () => { gateMsg.textContent = "The check didn't go through. Close this and press Download again." },
    'expired-callback': () => ts.reset(widget),
  })
}
// ponytail: until the Turnstile site key is set on Vercel, the button keeps the old public link so downloads never
// break; once VITE_TURNSTILE_SITEKEY is set and the site redeployed, the check takes over and the public copy goes
const UNGATED = 'https://pub-5acacfe7cd8e49899759f66d80609421.r2.dev/downloads/YT-Clipper-Setup.exe'
$$<HTMLAnchorElement>('[data-download]').forEach((a) => {
  if (!SITEKEY) { a.href = UNGATED; return }
  a.href = GATE
  a.addEventListener('click', (e) => { e.preventDefault(); openGate() })
})
$('[data-gate-close]', gate).addEventListener('click', () => gate.close())
gate.addEventListener('click', (e) => { if (e.target === gate) gate.close() })  // a click on the backdrop
