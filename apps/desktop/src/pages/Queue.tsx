// The content queue (PRD §46): every piece across projects at its current stage, with jobs that are working now.
import { useState } from 'react'
import { call, formatDate, label, useQuery, type PieceStatus, type QueueData } from '../lib/studio'
import { Button, ErrorNote, PageHeader, cx } from '../components/ui'

const STAGES: { id: PieceStatus; text: string }[] = [
  { id: 'rendering', text: 'Rendering' },
  { id: 'written', text: 'Needs render' },
  { id: 'ready', text: 'Ready' },
  { id: 'approved', text: 'Approved' },
  { id: 'exported', text: 'Exported' },
  { id: 'failed', text: 'Failed' },
]

export function Queue({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, error, reload } = useQuery<QueueData>('queue.list')
  const [stage, setStage] = useState<PieceStatus>('ready')
  const pieces = data?.pieces.filter((p) => p.status === stage) ?? []
  const counts = Object.fromEntries(STAGES.map((s) => [s.id, data?.pieces.filter((p) => p.status === s.id).length ?? 0]))
  const working = data?.jobs.filter((j) => j.status === 'queued' || j.status === 'running') ?? []

  return (
    <>
      <PageHeader title="Queue">
        <Button variant="ghost" onClick={reload}>Refresh</Button>
      </PageHeader>
      {error && <div className="mb-6"><ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} /></div>}

      {working.length > 0 && (
        <section aria-live="polite" className="glass mb-5 grid gap-3 px-7 py-5">
          {working.map((j) => (
            <div key={j.id} className="grid gap-1.5">
              <div className="flex items-center justify-between gap-4 text-[13px]">
                <span className="text-ink">{j.project} · {j.stage || 'Starting'}</span>
                <Button variant="ghost" onClick={() => call('jobs.cancel', { id: j.id }).then(reload)}>Cancel</Button>
              </div>
              <div className="h-0.5 overflow-hidden rounded-full bg-line" role="progressbar"
                aria-valuenow={Math.round(j.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
                <div className="h-full origin-left bg-accent transition-transform duration-500 ease-out-expo"
                  style={{ transform: `scaleX(${Math.max(j.progress, 0.02)})` }} />
              </div>
            </div>
          ))}
        </section>
      )}

      <div role="tablist" aria-label="Queue stages" className="mb-5 flex flex-wrap gap-1.5">
        {STAGES.map((s) => (
          <button key={s.id} role="tab" aria-selected={stage === s.id} onClick={() => setStage(s.id)}
            className={cx('no-drag flex h-9 items-center gap-2 rounded-control border px-4 text-[13px] transition-colors duration-150',
              stage === s.id ? 'border-transparent bg-ink font-medium text-ground' : 'border-line bg-white/[0.03] text-ink-2 hover:border-line-strong hover:text-ink')}>
            {s.text}
            <span className={cx('tnum text-2xs', stage === s.id ? 'opacity-70' : 'text-ink-3')}>{counts[s.id]}</span>
          </button>
        ))}
      </div>

      {pieces.length === 0 ? (
        <p className="py-12 text-[13px] text-ink-3">Nothing here right now.</p>
      ) : (
        <ol className="glass px-8 py-2">
          {pieces.map((p) => (
            <li key={p.id}>
              <button onClick={() => onOpen(p.project_id)}
                className="grid w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-6 border-t border-line py-5 text-left first:border-t-0">
                <span className="tnum text-xs text-ink-3">{String(p.idx).padStart(3, '0')}</span>
                <span className="min-w-0">
                  <span className="block truncate text-[14px] text-ink">{p.quote}</span>
                  <span className="text-xs text-ink-3">{p.project} · {formatDate(p.created_at)}</span>
                </span>
                <span className="text-xs text-ink-3">
                  {p.renders > 0 ? `${p.renders} render${p.renders === 1 ? '' : 's'}` : label(p.status)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </>
  )
}
