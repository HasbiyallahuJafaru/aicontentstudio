// The content queue (PRD §46): every piece across projects at its current stage, with jobs that are working now.
import { Fragment, useState, type CSSProperties } from 'react'
import { CaretRight } from '@phosphor-icons/react'
import { call, formatDate, label, useQuery, type PieceStatus, type QueueData } from '../lib/studio'
import { Button, ErrorNote, PageHeader, cx } from '../components/ui'
import { Cover } from '../components/Cover'

const STAGES: { id: PieceStatus; text: string }[] = [
  { id: 'rendering', text: 'Rendering' },
  { id: 'written', text: 'Needs render' },
  { id: 'ready', text: 'Ready' },
  { id: 'exported', text: 'Exported' },
  { id: 'failed', text: 'Failed' },
]

const EMPTY: Record<PieceStatus, string> = {
  rendering: 'Nothing is rendering. Renders you start appear here live.',
  written: 'Every written piece has a render. New pieces wait here until you render them.',
  ready: 'No rendered pieces waiting to be posted or exported.',
  exported: 'Nothing exported yet.',
  failed: 'Nothing has failed.',
}

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
        <section aria-live="polite" className="glass anim-drift mb-6 grid gap-4 px-7 py-5">
          {working.map((j) => (
            <div key={j.id} className="grid gap-2">
              <div className="flex items-center justify-between gap-4 text-[13px]">
                <span className="min-w-0 truncate"><span className="font-medium text-ink">{j.project}</span>
                  <span className="text-ink-3"> · {j.stage || 'Starting'}</span></span>
                <span className="flex shrink-0 items-center gap-3">
                  <span className="tnum text-xs text-accent-ink">{Math.round(j.progress * 100)}%</span>
                  <Button variant="ghost" onClick={() => call('jobs.cancel', { id: j.id }).then(reload)}>Cancel</Button>
                </span>
              </div>
              <div className="h-[3px] overflow-hidden rounded-full bg-black/[0.08]" role="progressbar"
                aria-valuenow={Math.round(j.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
                <div className="h-full origin-left rounded-full bg-pop transition-transform duration-500 ease-[var(--ease-premium)]"
                  style={{ transform: `scaleX(${Math.max(j.progress, 0.02)})` }} />
              </div>
            </div>
          ))}
        </section>
      )}

      {/* the stages read as one pipeline: a single track, each stage a step along it */}
      <div role="tablist" aria-label="Queue stages"
        className="mb-7 flex w-fit max-w-full flex-wrap items-center gap-0.5 rounded-[18px] bg-black/[0.05] p-1 shadow-[inset_0_0_0_1px_rgb(17_18_20/0.06)]">
        {STAGES.map((s, i) => (
          <Fragment key={s.id}>
            {i > 0 && s.id !== 'failed' && <CaretRight aria-hidden size={10} className="mx-0.5 text-ink-3/60" />}
            {s.id === 'failed' && <span aria-hidden className="mx-1.5 h-4 w-px bg-line-strong" />}
            <button role="tab" aria-selected={stage === s.id} onClick={() => setStage(s.id)}
              className={cx('no-drag flex h-9 items-center gap-2 rounded-[14px] px-4 text-[13px] transition-[background-color,color] duration-200',
                stage === s.id ? 'chip-on' : 'text-ink-2 hover:bg-black/[0.06] hover:text-ink')}>
              {s.text}
              <span className={cx('tnum text-2xs', stage === s.id ? 'opacity-70'
                : counts[s.id] && (s.id === 'failed' ? 'text-danger' : s.id === 'rendering' ? 'text-accent-ink' : 'text-ink-2') || 'text-ink-3')}>
                {counts[s.id]}
              </span>
            </button>
          </Fragment>
        ))}
      </div>

      {pieces.length === 0 ? (
        <p key={stage} className="anim-drift py-16 text-center text-[13px] text-ink-3">{EMPTY[stage]}</p>
      ) : (
        <ol key={stage} className="grid grid-cols-[repeat(auto-fill,minmax(176px,1fr))] gap-x-5 gap-y-7">
          {pieces.map((p, i) => (
            <li key={p.id} className="anim-slot" style={{ '--i': Math.min(i, 12) } as CSSProperties}>
              <button onClick={() => onOpen(p.project_id)} className="group grid w-full gap-3 text-left">
                <div className="relative">
                  <Cover src={p.cover} quote={p.quote} className="transition-transform duration-300 ease-[var(--ease-premium)] group-hover:-translate-y-1" />
                  <span className="tnum absolute left-3 top-3 rounded-full bg-black/55 px-2 py-0.5 text-2xs font-medium text-white backdrop-blur">
                    {String(p.idx).padStart(3, '0')}
                  </span>
                </div>
                <span className="grid gap-1 px-1">
                  {/* the line is the piece's identity: always shown, even when the cover is a rendered image */}
                  {p.cover && <span className="line-clamp-2 text-[13px] leading-snug font-medium text-ink">{p.quote}</span>}
                  <span className="truncate text-xs text-ink-3">
                    {p.project} · {p.renders > 0 ? `${p.renders} render${p.renders === 1 ? '' : 's'}` : label(p.status)} · {formatDate(p.created_at)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </>
  )
}
