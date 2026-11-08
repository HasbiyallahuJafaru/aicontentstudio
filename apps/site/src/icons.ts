// Phosphor icons, inlined as SVG wherever the markup has <i data-icon="name">. Shared by every page.
import arrowDownRight from '@phosphor-icons/core/assets/regular/arrow-down-right.svg?raw'
import calendarCheck from '@phosphor-icons/core/assets/regular/calendar-check.svg?raw'
import githubLogo from '@phosphor-icons/core/assets/regular/github-logo.svg?raw'
import globe from '@phosphor-icons/core/assets/regular/globe.svg?raw'
import linkedinLogo from '@phosphor-icons/core/assets/regular/linkedin-logo.svg?raw'
import lockSimple from '@phosphor-icons/core/assets/regular/lock-simple.svg?raw'
import microphone from '@phosphor-icons/core/assets/regular/microphone.svg?raw'
import plus from '@phosphor-icons/core/assets/regular/plus.svg?raw'
import scissors from '@phosphor-icons/core/assets/regular/scissors.svg?raw'
import arrowRight from '@phosphor-icons/core/assets/regular/arrow-right.svg?raw'
import filmStrip from '@phosphor-icons/core/assets/regular/film-strip.svg?raw'
import play from '@phosphor-icons/core/assets/fill/play-fill.svg?raw'
import sparkle from '@phosphor-icons/core/assets/fill/sparkle-fill.svg?raw'
import textAa from '@phosphor-icons/core/assets/regular/text-aa.svg?raw'
import windowsLogo from '@phosphor-icons/core/assets/regular/windows-logo.svg?raw'

const ICONS: Record<string, string> = {
  'arrow-down-right': arrowDownRight, 'calendar-check': calendarCheck, 'github-logo': githubLogo, globe,
  'linkedin-logo': linkedinLogo, 'lock-simple': lockSimple, microphone, plus, scissors, 'windows-logo': windowsLogo,
  'arrow-right': arrowRight, 'film-strip': filmStrip, play, sparkle, 'text-aa': textAa,
}

export function injectIcons(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>('i[data-icon]').forEach((el) => {
    el.innerHTML = ICONS[el.dataset.icon!] ?? ''
    el.setAttribute('aria-hidden', 'true')
  })
}
