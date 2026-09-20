import type { ReactNode } from 'react'
import { Aperture, CornersIn, Export, Folders, GearSix, Images, ListChecks, PlusCircle, SquaresFour, type Icon } from '@phosphor-icons/react'
import { studio, useBackendStatus, useFullScreen } from '../lib/studio'
import { CreatedBy } from '../components/Branding'
import { Button, ErrorNote, cx } from '../components/ui'

export type Page = 'dashboard' | 'create' | 'projects' | 'project' | 'library' | 'queue' | 'exports' | 'settings'

const NAV: { id: Page; label: string; icon: Icon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: SquaresFour },
  { id: 'create', label: 'Create', icon: PlusCircle },
  { id: 'projects', label: 'Projects', icon: Folders },
  { id: 'library', label: 'Library', icon: Images },
  { id: 'queue', label: 'Queue', icon: ListChecks },
  { id: 'exports', label: 'Exports', icon: Export },
]

function RailItem({ id, label, icon: I, active, onClick }: { id: Page; label: string; icon: Icon; active: boolean; onClick: (p: Page) => void }) {
  return (
    <button
      onClick={() => onClick(id)}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={cx(
        'no-drag group relative grid size-11 place-items-center rounded-2xl transition-[background-color,color,transform] duration-150 active:scale-95',
        active ? 'bg-white/[0.11] text-ink shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1)]' : 'text-ink-3 hover:bg-white/[0.06] hover:text-ink',
      )}
    >
      <I size={20} weight={active ? 'fill' : 'regular'}
        className="transition-transform duration-700 ease-out-expo group-hover:rotate-[360deg]" />
      <span aria-hidden
        className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-x-3 -translate-y-1/2 whitespace-nowrap rounded-field bg-black/90 px-2.5 py-1 text-2xs font-medium text-ink opacity-0 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.12),0_8px_24px_-8px_rgb(0_0_0/0.8)] transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
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
      className="no-drag group relative grid size-9 shrink-0 place-items-center rounded-full transition-colors duration-150 hover:bg-white/[0.06]">
      <span className="relative grid place-items-center">
        {beating && <span aria-hidden className={cx('absolute size-2 rounded-full opacity-60 motion-safe:animate-ping', color)} />}
        <span className={cx('relative size-2 rounded-full', color)} />
      </span>
      <span className="sr-only">{text}</span>
      <span aria-hidden
        className="pointer-events-none absolute right-full top-1/2 z-50 mr-1 -translate-y-1/2 translate-x-3 whitespace-nowrap rounded-field bg-black/90 px-2.5 py-1 text-2xs font-medium text-ink opacity-0 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.12),0_8px_24px_-8px_rgb(0_0_0/0.8)] transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
        {text}
      </span>
    </div>
  )
}

/** Fullscreen hides the window controls, so this is the only way back out besides F11 and Escape. */
function ExitFullScreen() {
  if (!useFullScreen()) return null
  return (
    <Button variant="ghost" onClick={() => studio.exitFullScreen()} className="no-drag h-8 !px-3 !text-xs">
      <CornersIn size={14} />Exit fullscreen
    </Button>
  )
}

export function Shell({ page, onNavigate, children }: { page: Page; onNavigate: (p: Page) => void; children: ReactNode }) {
  const status = useBackendStatus()
  return (
    <div className="ambient grain grid h-full grid-cols-[76px_minmax(0,1fr)] grid-rows-[44px_minmax(0,1fr)] overflow-hidden">
      <header className="drag titlebar-inset col-span-2 flex items-center gap-3 pl-5">
        <Aperture size={20} weight="fill" className="text-accent" />
        <span className="font-display text-[13px] font-semibold tracking-[-0.01em]">AI Social Content Studio</span>
        <div className="ml-auto flex items-center gap-1"><ExitFullScreen /><BackendIndicator /></div>
      </header>

      <nav aria-label="Main" className="mb-3 ml-3 flex flex-col items-center gap-2 rounded-[24px] bg-black/35 py-3 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.06)]">
        {NAV.map((n) => <RailItem key={n.id} {...n} active={page === n.id || (n.id === 'projects' && page === 'project')} onClick={onNavigate} />)}
        <div className="mt-auto">
          <RailItem id="settings" label="Settings" icon={GearSix} active={page === 'settings'} onClick={onNavigate} />
        </div>
      </nav>

      <main className="relative mx-3 mb-3 min-w-0 overflow-x-hidden overflow-y-auto rounded-[30px] bg-white/[0.025] shadow-[inset_0_0_0_1px_rgb(255_244_232/0.06)]">
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
