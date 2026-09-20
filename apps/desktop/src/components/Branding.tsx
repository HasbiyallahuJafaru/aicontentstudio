// Developer branding (PRD): interactive SVG logos for the website, LinkedIn and GitHub.
// Shared by the splash (lower-left corner) and the "created by" footer on every Shell page.
import { useEffect, useState } from 'react'
import { studio } from '../lib/studio'
import { cx } from './ui'

export const LINKS = [
  { id: 'website', label: 'Website', url: 'https://hasbiyallahu.xyz',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.6 2.6 3.9 5.6 3.9 9S14.6 18.4 12 21M12 3C9.4 5.6 8.1 8.6 8.1 12s1.3 6.4 3.9 9" />
      </svg>
    ) },
  { id: 'linkedin', label: 'LinkedIn', url: 'https://www.linkedin.com/in/hasbiyallahu-jafaru/',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.36V9h3.41v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12ZM7.12 20.45H3.56V9h3.56v11.45Z" />
      </svg>
    ) },
  { id: 'github', label: 'GitHub', url: 'https://github.com/HasbiyallahuJafaru',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M12 2C6.48 2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49 0-.24-.01-.88-.01-1.72-2.78.62-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.5-1.11-1.5-.91-.63.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.37-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.7 0 0 .84-.28 2.75 1.05a9.36 9.36 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.4.2 2.44.1 2.7.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.8-4.57 5.06.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.6.69.49A10.06 10.06 0 0 0 22 12.25C22 6.58 17.52 2 12 2Z" />
      </svg>
    ) },
] as const

/** Icons take turns in the spotlight: the focused one sits at full size, the rest shrink back.
 * Pauses while the pointer is over the strip, and never auto-plays under reduced motion. */
export function SocialLinks({ size = 18 }: { size?: number }) {
  const [focus, setFocus] = useState(0)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (paused || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const t = setInterval(() => setFocus((i) => (i + 1) % LINKS.length), 3000)
    return () => clearInterval(t)
  }, [paused])

  return (
    <div className="flex items-center gap-1.5"
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      {LINKS.map((l, i) => (
        <a key={l.id} href={l.url} aria-label={l.label}
          onClick={(e) => { e.preventDefault(); studio.openExternal(l.url) }}
          className={cx('no-drag group relative grid size-9 place-items-center rounded-2xl',
            'transition-[color,background-color,transform] duration-500 hover:bg-white/[0.08] hover:text-ink active:scale-95',
            i === focus ? 'text-ink' : 'text-ink-3')}>
          <span style={{ width: size, height: size, scale: i === focus ? 1 : 0.68 }}
            className={cx('block transition-[scale] duration-500 ease-out-expo [&>svg]:size-full',
              i === focus && 'anim-vibrate')}>{l.icon}</span>
          <span aria-hidden
            className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 translate-y-1 whitespace-nowrap rounded-field bg-black/90 px-2.5 py-1 text-2xs font-medium text-ink opacity-0 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.12),0_8px_24px_-8px_rgb(0_0_0/0.8)] transition-all duration-150 group-hover:translate-y-0 group-hover:opacity-100">
            {l.label}
          </span>
        </a>
      ))}
    </div>
  )
}

/** The "created by" strip at the bottom of every page. */
export function CreatedBy() {
  return (
    <footer className="mt-10 flex items-center justify-center gap-2 pb-2 text-xs text-ink-3">
      <span>Created by Hasbiyallahu Jafaru</span>
      <SocialLinks size={15} />
    </footer>
  )
}
