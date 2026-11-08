import '@fontsource-variable/geist'
import './style.css'
import { injectIcons } from './icons'

// Downloads go through a Cloudflare Turnstile check: the widget's single-use token is handed to the download Worker
// (apps/download-worker), which verifies it and streams the installer from a private bucket. There is no public file.
const GATE = import.meta.env.VITE_DOWNLOAD_GATE || 'https://ytclipper-download.jafaruhasbiyallahu-cc1.workers.dev/download'
// the widget's public site key; Cloudflare's always-pass test key in local dev only
const SITEKEY = import.meta.env.VITE_TURNSTILE_SITEKEY || (import.meta.env.DEV ? '1x00000000000000000000AA' : '')
const RENDERS = Object.values(import.meta.glob('./assets/renders/*.webp', { eager: true, import: 'default' })) as string[]
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches

injectIcons()

// the hero scene loads after first paint, so the headline and button never wait on three.js
const canvas = document.querySelector<HTMLCanvasElement>('.hero-canvas')!
requestIdleCallback?.(() => import('./hero').then(({ mountHero }) => mountHero(canvas, RENDERS)), { timeout: 600 })
  ?? import('./hero').then(({ mountHero }) => mountHero(canvas, RENDERS))

// the nav gains its panel once the page leaves the top
const nav = document.querySelector('[data-nav]')!
new IntersectionObserver(([e]) => nav.classList.toggle('scrolled', !e.isIntersecting))
  .observe(document.querySelector('.top-sentinel')!)

// reveal on entry: each block rises in once, the first time it is seen
const reveal = new IntersectionObserver((entries) => entries.forEach((e) => {
  if (!e.isIntersecting) return
  e.target.classList.add('in')
  reveal.unobserve(e.target)
}), { rootMargin: '0px 0px -10% 0px' })
document.querySelectorAll('[data-reveal]').forEach((el) => (reduce ? el.classList.add('in') : reveal.observe(el)))

// how it works: the step whose screenshot holds the middle of the screen is the one lit in the rail
const steps = document.querySelectorAll<HTMLElement>('.how-steps li')
const howObserver = new IntersectionObserver((entries) => entries.forEach((e) => {
  if (!e.isIntersecting) return
  const i = (e.target as HTMLElement).dataset.step
  steps.forEach((s) => s.classList.toggle('active', s.dataset.step === i))
}), { rootMargin: '-45% 0px -45% 0px' })
document.querySelectorAll('.how-media figure').forEach((f) => howObserver.observe(f))

// the gallery: every render once, then the same set again so the loop is seamless
const track = document.querySelector('.marquee-track')!
const tile = (src: string, hidden: boolean) =>
  `<img src="${src}" alt="${hidden ? '' : 'A quote image made by the studio'}" loading="lazy" decoding="async" ${hidden ? 'aria-hidden="true"' : ''} />`
track.innerHTML = RENDERS.map((s) => tile(s, false)).join('') + RENDERS.map((s) => tile(s, true)).join('')

// the download check: a native dialog holding the Turnstile widget, loaded on first use so it costs nothing up front
type Turnstile = { render(el: HTMLElement, o: object): string; reset(id?: string): void; remove(id: string): void }
const gate = document.querySelector<HTMLDialogElement>('[data-gate]')!
const gateMsg = gate.querySelector<HTMLElement>('[data-gate-msg]')!
const slot = gate.querySelector<HTMLElement>('[data-turnstile]')!
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
document.querySelectorAll<HTMLAnchorElement>('[data-download]').forEach((a) => {
  if (!SITEKEY) { a.href = UNGATED; return }
  a.href = GATE
  a.addEventListener('click', (e) => { e.preventDefault(); openGate() })
})
gate.querySelector('[data-gate-close]')!.addEventListener('click', () => gate.close())
gate.addEventListener('click', (e) => { if (e.target === gate) gate.close() })  // a click on the backdrop
