import type { ReactNode } from 'react'
import { Aperture, Export, Folders, GearSix, Images, ListChecks, PlusCircle, SquaresFour, type Icon } from '@phosphor-icons/react'
import { studio, useBackendStatus } from '../lib/studio'
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
      title={label}
      aria-current={active ? 'page' : undefined}
      className={cx(
        'no-drag grid size-11 place-items-center rounded-2xl transition-[background-color,color,transform] duration-150 active:scale-95',
        active ? 'bg-white/[0.11] text-ink shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1)]' : 'text-ink-3 hover:bg-white/[0.06] hover:text-ink',
      )}
    >
      <I size={20} weight={active ? 'fill' : 'regular'} />
    </button>
  )
}

function BackendIndicator() {
  const s = useBackendStatus()
  const text = { starting: 'Starting engine', ready: 'Engine ready', crashed: 'Engine stopped', stopped: 'Engine stopped' }[s.state]
  const color = { starting: 'bg-accent', ready: 'bg-ok', crashed: 'bg-danger', stopped: 'bg-ink-3' }[s.state]
  return (
    <div className="flex items-center gap-2 rounded-full bg-white/[0.05] px-3 py-1 text-xs text-ink-2" role="status" aria-live="polite">
      <span className={cx('size-1.5 rounded-full', color, s.state === 'starting' && 'animate-pulse')} />
      {text}
    </div>
  )
}

export function Shell({ page, onNavigate, children }: { page: Page; onNavigate: (p: Page) => void; children: ReactNode }) {
  const status = useBackendStatus()
  return (
    <div className="ambient grain grid h-full grid-cols-[76px_minmax(0,1fr)] grid-rows-[44px_minmax(0,1fr)] overflow-hidden">
      <header className="drag titlebar-inset col-span-2 flex items-center gap-3 pl-5">
        <Aperture size={20} weight="fill" className="text-accent" />
        <span className="font-display text-[13px] font-semibold tracking-[-0.01em]">AI Social Content Studio</span>
        <div className="ml-auto"><BackendIndicator /></div>
      </header>

      <nav aria-label="Main" className="mb-3 ml-3 flex flex-col items-center gap-2 rounded-[24px] bg-black/35 py-3 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.06)]">
        {NAV.map((n) => <RailItem key={n.id} {...n} active={page === n.id || (n.id === 'projects' && page === 'project')} onClick={onNavigate} />)}
        <div className="mt-auto">
          <RailItem id="settings" label="Settings" icon={GearSix} active={page === 'settings'} onClick={onNavigate} />
        </div>
      </nav>

      <main className="relative mx-3 mb-3 min-w-0 overflow-x-hidden overflow-y-auto rounded-[30px] bg-white/[0.025] shadow-[inset_0_0_0_1px_rgb(255_244_232/0.06)]">
        <div className="mx-auto max-w-[1240px] px-10 pt-9 pb-12">
          {status.message && status.state !== 'ready' && (
            <div className="mb-6">
              <ErrorNote
                error={{ message: status.message, detail: status.detail }}
                action={status.state === 'crashed' && <Button onClick={() => studio.restart()}>Restart engine</Button>}
              />
            </div>
          )}
          {children}
        </div>
      </main>
    </div>
  )
}
