import type { CSSProperties, ReactNode } from 'react'
import { Aperture, CopySimple, Export, Folders, GearSix, Images, ListChecks, Minus, PlusCircle, SquaresFour, X, type Icon } from '@phosphor-icons/react'
import { studio, useBackendStatus, useFullScreen } from '../lib/studio'
import { CreatedBy } from '../components/Branding'
import { Button, ErrorNote, cx } from '../components/ui'
import { DomeBackground } from '../components/DomeBackground'
import { CreatorCard } from '../components/CreatorCard'

// the background dome plays short looping clips (2.5 s animated WebP, built by scripts/make-dome-clips.py from free
// Pexels footage, credits in assets/dome/CREDITS.json) so the room feels like video, not repeated posters
const CLIPS = Object.values(import.meta.glob('../assets/dome/clip-*.webp', { eager: true, import: 'default' })) as string[]


export type Page = 'dashboard' | 'create' | 'projects' | 'project' | 'library' | 'queue' | 'exports' | 'settings'

const NAV: { id: Page; label: string; icon: Icon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: SquaresFour },
  { id: 'create', label: 'Create', icon: PlusCircle },
  { id: 'projects', label: 'Projects', icon: Folders },
  { id: 'library', label: 'Library', icon: Images },
  { id: 'queue', label: 'Queue', icon: ListChecks },
  { id: 'exports', label: 'Exports', icon: Export },
]

function RailItem({ id, label, icon: I, active, onClick, i = 0 }: { id: Page; label: string; icon: Icon; active: boolean; onClick: (p: Page) => void; i?: number }) {
  return (
    <button
      style={{ '--i': i } as CSSProperties}
      onClick={() => onClick(id)}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={cx(
        'no-drag group relative grid size-11 place-items-center rounded-2xl transition-[background-color,color,transform] duration-150 active:scale-95',
        active ? 'bg-accent text-on-accent' : 'text-white/60 hover:bg-white/[0.1] hover:text-white',
      )}
    >
      <I size={20} weight={active ? 'fill' : 'regular'}
        className="transition-transform duration-700 ease-out-expo group-hover:rotate-[360deg]" />
      <span aria-hidden
        className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-x-3 -translate-y-1/2 whitespace-nowrap rounded-field bg-ink px-2.5 py-1 text-2xs font-medium text-white opacity-0 shadow-[0_8px_24px_-12px_rgb(17_18_20/0.5)] transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
        {label}
      </span>
    </button>
  )
}

/** A live dot, like the rail icons: the state is the colour, the words wait for a hover. */
function BackendIndicator() {
  const s = useBackendStatus()
  const text = { starting: 'Starting engine', ready: 'Engine ready', crashed: 'Engine stopped', stopped: 'Engine stopped' }[s.state]
  const color = { starting: 'bg-accent', ready: 'bg-ok', crashed: 'bg-danger', stopped: 'bg-ink-3' }[s.state]
  const beating = s.state === 'ready' || s.state === 'starting'
  return (
    <div role="status" aria-live="polite"
      className="no-drag group relative grid size-9 shrink-0 place-items-center rounded-full transition-colors duration-150 hover:bg-black/[0.05]">
      <span className="relative grid place-items-center">
        {beating && <span aria-hidden className={cx('absolute size-2 rounded-full opacity-60 motion-safe:animate-ping', color)} />}
        <span className={cx('relative size-2 rounded-full', color)} />
      </span>
      <span className="sr-only">{text}</span>
      <span aria-hidden
        className="pointer-events-none absolute right-full top-1/2 z-50 mr-1 -translate-y-1/2 translate-x-3 whitespace-nowrap rounded-field bg-ink px-2.5 py-1 text-2xs font-medium text-white opacity-0 shadow-[0_8px_24px_-12px_rgb(17_18_20/0.5)] transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
        {text}
      </span>
    </div>
  )
}

/** Windows hides its own caption buttons in fullscreen (and maximize is fullscreen here), so the bar draws the same
 * three in the same corner: minimize, restore (leave fullscreen), close. Outside fullscreen the native ones show. */
function WindowControls() {
  const cls = 'no-drag grid h-11 w-[46px] place-items-center text-ink-2 transition-colors duration-150 hover:bg-black/[0.06] hover:text-ink'
  return (
    <div className="flex">
      <button type="button" aria-label="Minimize" className={cls} onClick={() => studio.minimize()}><Minus size={14} /></button>
      <button type="button" aria-label="Restore" className={cls} onClick={() => studio.exitFullScreen()}><CopySimple size={14} /></button>
      <button type="button" aria-label="Close" className={cx(cls, 'hover:bg-[#c42b1c] hover:text-white')} onClick={() => studio.close()}><X size={14} /></button>
    </div>
  )
}

export function Shell({ page, onNavigate, children }: { page: Page; onNavigate: (p: Page) => void; children: ReactNode }) {
  const status = useBackendStatus()
  const full = useFullScreen()
  return (
    <div className="ambient relative isolate grid h-full grid-cols-[76px_minmax(0,1fr)] grid-rows-[44px_minmax(0,1fr)] overflow-hidden">
      {/* the room's background: a dome of short looping clips turning slowly behind the pages (owner request 2026-11-08) */}
      <div className="absolute inset-0 -z-10"><DomeBackground images={CLIPS} /></div>
      <CreatorCard />
      {/* windowed: room for the native caption buttons; fullscreen: ours sit flush in the top-right corner */}
      <header className={cx('anim-shell-head drag col-span-2 flex items-center gap-3 bg-ground pl-5', full ? 'pr-0' : 'titlebar-inset')}>
        <span className="grid size-7 place-items-center rounded-[9px] bg-ink"><Aperture size={16} weight="fill" className="text-accent" /></span>
        <span className="font-display text-[13px] font-semibold tracking-[-0.01em]">AI Social Content Studio</span>
        <div className="ml-auto flex h-full items-center gap-3"><BackendIndicator />{full && <WindowControls />}</div>
      </header>

      {/* z-20: the rail's hover labels stick out over the page, so its layer must sit above the page's */}
      <nav aria-label="Main" className="anim-shell-rail relative z-20 mb-3 ml-3 flex flex-col items-center gap-2 rounded-[24px] bg-ink py-3">
        {NAV.map((n, i) => <RailItem key={n.id} {...n} i={i} active={page === n.id || (n.id === 'projects' && page === 'project')} onClick={onNavigate} />)}
        <div className="mt-auto" style={{ '--i': NAV.length } as CSSProperties}>
          <RailItem id="settings" label="Settings" icon={GearSix} active={page === 'settings'} onClick={onNavigate} />
        </div>
      </nav>

      <main className="anim-shell-main relative mx-3 mb-3 min-w-0 overflow-x-hidden overflow-y-auto rounded-[30px]">
        <div className="mx-auto flex min-h-full max-w-[1240px] flex-col px-10 pt-9 pb-6">
          {status.message && status.state !== 'ready' && (
            <div className="mb-6">
              <ErrorNote
                error={{ message: status.message, detail: status.detail }}
                action={status.state === 'crashed' && <Button onClick={() => studio.restart()}>Restart engine</Button>}
              />
            </div>
          )}
          <div className="min-w-0 flex-1">{children}</div>
          <CreatedBy />
        </div>
      </main>
    </div>
  )
}
