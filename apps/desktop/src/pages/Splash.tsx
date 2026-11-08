import { lazy, Suspense, useState, type ComponentType, type CSSProperties } from 'react'
import { SocialLinks } from '../components/Branding'
import { TiltedTiles } from '../components/TiltedTiles'
import { Button, Reveal, cx } from '../components/ui'

// typed loosely: the vendored file is untyped and its `images = []` default would infer never[]
const BounceCards = lazy(() => import('../components/BounceCards')) as unknown as ComponentType<Record<string, unknown>>
// the fan: five quote images the studio's own design engine rendered (app/design.py), bundled so the splash
// shows real output before the engine has even started
const RENDERS = Object.values(import.meta.glob('../assets/splash/card-*.webp', { eager: true, import: 'default' })) as string[]
const CARDS = RENDERS.slice(0, 5)
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
    <div className="ambient relative h-full overflow-hidden">
      {/* a tilted wall of the studio's own renders drifting past (owner request 2026-11-08); it swells away on the way in */}
      <div aria-hidden className={leaving ? 'anim-splash-bg-out absolute inset-0' : 'anim-fade absolute inset-0'}>
        <TiltedTiles images={RENDERS} />
      </div>

      {/* the content sits on one solid white panel over the wall: flat, no scrim */}
      <div className="relative grid h-full place-items-center px-10">
      <div className={cx('grid justify-items-center gap-7 rounded-[32px] bg-panel px-14 pt-10 pb-12 text-center shadow-[0_30px_80px_-40px_rgb(17_18_20/0.55)]',
        leaving && 'anim-splash-out')}>
        <Suspense fallback={<div style={{ width: 560, height: 250 }} />}>
          <BounceCards images={CARDS} containerWidth={560} containerHeight={250}
            cardSize={190} spread={92} rotation={8} arc={0} pushDistance={150} hoverScale={1.07} bounciness={0.6}
            animationDelay={0.15} animationStagger={0.07} borderWidth={4} borderColor="#ffffff" radius={18} shadow enableHover />
        </Suspense>
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
      </div>

      <div className={cx('absolute bottom-4 left-5 rounded-full bg-panel px-1.5 py-1', leaving ? 'anim-splash-out' : 'anim-drift')} style={at(1000)}>
        <SocialLinks size={17} />
      </div>
    </div>
  )
}
