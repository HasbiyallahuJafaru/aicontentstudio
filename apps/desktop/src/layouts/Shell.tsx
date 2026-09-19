import type { ReactNode } from 'react'
import { FilmSlate, Folders, GearSix, PlusSquare, SquaresFour, type Icon } from '@phosphor-icons/react'
import { studio, useBackendStatus } from '../lib/studio'
import { Button, ErrorNote, cx } from '../components/ui'

export type Page = 'dashboard' | 'create' | 'projects' | 'settings'

// Library, Queue and Exports join this list in the phases that give them real content.
const NAV: { id: Page; label: string; icon: Icon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: SquaresFour },
  { id: 'create', label: 'Create', icon: PlusSquare },
  { id: 'projects', label: 'Projects', icon: Folders },
]

const TITLES: Record<Page, string> = { dashboard: 'Dashboard', create: 'New project', projects: 'Projects', settings: 'Settings' }

function NavItem({ id, label, icon: I, active, onClick }: { id: Page; label: string; icon: Icon; active: boolean; onClick: (p: Page) => void }) {
  return (
    <button
      onClick={() => onClick(id)}
      aria-current={active ? 'page' : undefined}
      className={cx(
        'flex h-8 w-full items-center gap-2.5 rounded-control px-2.5 text-[13px] transition-colors duration-150',
        active ? 'bg-raised text-ink' : 'text-ink-2 hover:bg-raised/60 hover:text-ink',
      )}
    >
      <I size={17} weight={active ? 'fill' : 'regular'} className={active ? 'text-ink' : 'text-ink-3'} />
      {label}
    </button>
  )
}

function BackendIndicator() {
  const s = useBackendStatus()
  const text = { starting: 'Starting engine', ready: 'Engine ready', crashed: 'Engine stopped', stopped: 'Engine stopped' }[s.state]
  const color = { starting: 'bg-accent', ready: 'bg-ok', crashed: 'bg-danger', stopped: 'bg-ink-3' }[s.state]
  return (
    <div className="flex items-center gap-2 text-xs text-ink-3" role="status" aria-live="polite">
      <span className={cx('size-1.5 rounded-full', color, s.state === 'starting' && 'animate-pulse')} />
      {text}
    </div>
  )
}

export function Shell({ page, onNavigate, children }: { page: Page; onNavigate: (p: Page) => void; children: ReactNode }) {
  const status = useBackendStatus()
  return (
    <div className="grid h-full grid-cols-[216px_1fr] grid-rows-[44px_1fr]">
      <header className="drag titlebar-inset col-span-2 flex items-center gap-3 border-b border-line bg-panel pl-4">
        <FilmSlate size={18} weight="fill" className="text-ink" />
        <span className="text-[13px] font-semibold tracking-[-0.01em]">AI Social Content Studio</span>
        <span className="text-ink-3">/</span>
        <span className="text-[13px] text-ink-2">{TITLES[page]}</span>
        <div className="ml-auto"><BackendIndicator /></div>
      </header>

      <nav aria-label="Main" className="flex flex-col gap-0.5 border-r border-line bg-panel p-3">
        {NAV.map((n) => <NavItem key={n.id} {...n} active={page === n.id} onClick={onNavigate} />)}
        <div className="mt-auto">
          <NavItem id="settings" label="Settings" icon={GearSix} active={page === 'settings'} onClick={onNavigate} />
        </div>
      </nav>

      <main className="overflow-y-auto">
        <div className="mx-auto max-w-[1180px] px-10 py-9">
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
