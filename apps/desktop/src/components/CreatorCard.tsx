// The creator card (owner request 2026-11-09): a React Bits Lanyard ID card that drops in after a render or clip job
// finishes, at most twice a day. The card art is drawn once by scripts/make-creator-card.py. three.js only loads
// when the card opens (lazy), so the app's first paint never pays for it.
import { lazy, Suspense, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from '@phosphor-icons/react'
import { studio, type Job } from '../lib/studio'
import { LINKS } from './Branding'
import { Button } from './ui'
import front from '../assets/lanyard/front.webp'
import back from '../assets/lanyard/back.webp'
import strap from '../assets/lanyard/strap.webp'

const Lanyard = lazy(() => import('./Lanyard'))
const KEY = 'acs.creatorCard'  // {"day": "YYYY-MM-DD", "count": n} in this viewer's localStorage
const PER_DAY = 2               // owner: twice a day
const CELEBRATE = new Set(['render', 'visuals_render', 'clip'])  // jobs that end in finished videos or images
const today = () => new Date().toLocaleDateString('sv')

function shownToday(): number {
  try {
    const seen = JSON.parse(localStorage.getItem(KEY) || 'null')
    return seen?.day === today() ? Number(seen.count) || 0 : 0
  } catch {
    return 0
  }
}

function markShown() {
  try { localStorage.setItem(KEY, JSON.stringify({ day: today(), count: shownToday() + 1 })) } catch { /* storage off: it may show again */ }
}

export function CreatorCard() {
  const [open, setOpen] = useState(false)

  useEffect(() => studio.onEvent((event, d) => {
    const job = d as Job
    if (event !== 'job.completed' || !CELEBRATE.has(job.kind ?? '') || shownToday() >= PER_DAY) return
    markShown()
    window.setTimeout(() => setOpen(true), 1200)  // let the finished work land on screen first
  }), [])

  useEffect(() => {  // opens on demand too (no daily limit): the smoke run checks the card renders this way
    const show = () => setOpen(true)
    window.addEventListener('creator-card:open', show)
    return () => window.removeEventListener('creator-card:open', show)
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!open) return null
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Created by Hasbiyallahu Jafaru" onClick={() => setOpen(false)}
      className="card-drop fixed inset-0 z-40 grid grid-rows-[minmax(0,1fr)_auto] bg-ink/40 backdrop-blur-sm">
      {/* the card hangs from the top edge; drag it, throw it, click it to flip */}
      <div className="relative min-h-0" onClick={(e) => e.stopPropagation()}>
        <Suspense fallback={null}>
          <Lanyard frontImage={front} backImage={back} strapImage={strap} cardColor="#ffffff" finish="glossy"
            metal="graphite" size={0.62} strapLength={0.42} strapWidth={0.75} breeze={0.35} peek style={{}} />
        </Suspense>
      </div>
      {/* owner: the three link icons, then a plain Close so it is obvious how to dismiss (Escape and a click outside work too) */}
      <div onClick={(e) => e.stopPropagation()} className="mx-auto mb-8 flex items-center justify-center gap-1 rounded-control bg-panel p-1.5
        shadow-[inset_0_0_0_1px_rgb(17_18_20/0.09),0_24px_60px_-24px_rgb(17_18_20/0.3)]">
        {LINKS.map((l) => (
          <Button key={l.id} variant="ghost" className="!size-11 justify-center !p-0" onClick={() => studio.openExternal(l.url)}
            aria-label={l.label} title={l.label}><span className="grid size-5 place-items-center [&>svg]:size-full">{l.icon}</span></Button>
        ))}
        <span aria-hidden className="mx-1.5 h-6 w-px bg-line" />
        <Button variant="primary" className="!h-11" onClick={() => setOpen(false)}><X size={14} weight="bold" />Close</Button>
      </div>
    </div>,
    document.body,
  )
}
