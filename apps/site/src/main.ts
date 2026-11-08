import '@fontsource-variable/geist'
import './style.css'
import arrowDownRight from '@phosphor-icons/core/assets/regular/arrow-down-right.svg?raw'
import calendarCheck from '@phosphor-icons/core/assets/regular/calendar-check.svg?raw'
import githubLogo from '@phosphor-icons/core/assets/regular/github-logo.svg?raw'
import globe from '@phosphor-icons/core/assets/regular/globe.svg?raw'
import linkedinLogo from '@phosphor-icons/core/assets/regular/linkedin-logo.svg?raw'
import lockSimple from '@phosphor-icons/core/assets/regular/lock-simple.svg?raw'
import microphone from '@phosphor-icons/core/assets/regular/microphone.svg?raw'
import plus from '@phosphor-icons/core/assets/regular/plus.svg?raw'
import scissors from '@phosphor-icons/core/assets/regular/scissors.svg?raw'
import windowsLogo from '@phosphor-icons/core/assets/regular/windows-logo.svg?raw'

// One place for the installer link: the asset attached to the latest GitHub release.
const DOWNLOAD_URL = 'https://github.com/HasbiyallahuJafaru/aicontentstudio/releases/latest/download/YT-Clipper-Setup.exe'
const RENDERS = Object.values(import.meta.glob('./assets/renders/*.webp', { eager: true, import: 'default' })) as string[]
const ICONS: Record<string, string> = {
  'arrow-down-right': arrowDownRight, 'calendar-check': calendarCheck, 'github-logo': githubLogo, globe,
  'linkedin-logo': linkedinLogo, 'lock-simple': lockSimple, microphone, plus, scissors, 'windows-logo': windowsLogo,
}
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches

document.querySelectorAll<HTMLElement>('i[data-icon]').forEach((el) => {
  el.innerHTML = ICONS[el.dataset.icon!] ?? ''
  el.setAttribute('aria-hidden', 'true')
})
document.querySelectorAll<HTMLAnchorElement>('[data-download]').forEach((a) => { a.href = DOWNLOAD_URL })

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
