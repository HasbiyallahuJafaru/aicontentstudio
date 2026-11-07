import { lazy, Suspense, useState, type CSSProperties } from 'react'
import { Aperture } from '@phosphor-icons/react'
import { SocialLinks } from '../components/Branding'
import { Button, Reveal } from '../components/ui'

// three.js loads in its own chunk: the title and button paint first, the living light fades in when ready
const Ember = lazy(() => import('../components/Ember'))
const LEAVE_MS = 420  // the content's exit; the studio's entrance takes over from there

const at = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties

export function Splash({ onCreate }: { onCreate: () => void }) {
  const [leaving, setLeaving] = useState(false)

  function enter() {
    if (leaving) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { onCreate(); return }
    setLeaving(true)
    setTimeout(onCreate, LEAVE_MS)
  }

  return (
    <div className="ambient grain relative h-full overflow-hidden">
      {/* the main page's own background, alive: drifting light and rising embers; it swells away on the way in */}
      <div aria-hidden className={leaving ? 'anim-splash-bg-out absolute inset-0' : 'anim-fade absolute inset-0'}>
        <Suspense fallback={null}><Ember live intensity={1.8} wave={0} /></Suspense>
      </div>
      {/* a soft vignette keeps the title readable over the brightest light */}
      <div className="absolute inset-0 bg-[radial-gradient(70%_55%_at_50%_45%,rgba(13_12_11/0.5),rgba(13_12_11/0.1)_70%,transparent)]" />

      <div className={leaving ? 'anim-splash-out relative grid h-full content-center justify-items-center gap-7 px-10 text-center'
        : 'relative grid h-full content-center justify-items-center gap-7 px-10 text-center'}>
        <div className="anim-drift" style={at(80)}>
          <Aperture size={40} weight="fill" className="text-accent drop-shadow-[0_2px_12px_rgba(0,0,0,0.45)]" />
        </div>
        <div className="grid gap-3">
          <h1 className="font-display text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] text-ink">
            <Reveal text="AI Social Content Studio" delay={260} step={80} />
          </h1>
          <p className="anim-drift mx-auto max-w-[52ch] text-[15px] leading-relaxed text-ink-2" style={at(640)}>
            A short brief becomes finished social content: quotes, narration, visuals and captions,
            written and kept entirely on your own computer.
          </p>
        </div>
        <div className="anim-drift mt-1" style={at(820)}>
          <Button variant="primary" onClick={enter}>Let&apos;s create content</Button>
        </div>
      </div>

      <div className={leaving ? 'anim-splash-out absolute bottom-4 left-5' : 'anim-drift absolute bottom-4 left-5'} style={at(1000)}>
        <SocialLinks size={17} />
      </div>
    </div>
  )
}
