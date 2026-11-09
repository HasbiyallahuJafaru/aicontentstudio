import type { Ref } from 'react'
import { useEffect, useRef, useState } from 'react'
import { Check, CircleNotch, Minus, X } from '@phosphor-icons/react'
import { call, type Job, type JobStep } from '../lib/studio'
import { Button, cx } from './ui'

const secs = (s: number) => (s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, '0')}s`)
const shown = (log: JobStep[]) => log.filter((s) => s.step !== 'Done')

/** The step that is running, ticking every second, so a stall shows as a growing number next to a named step. */
function useElapsed(key: string) {
  const [t, setT] = useState(0)
  useEffect(() => {
    setT(0)
    const start = Date.now()
    const id = setInterval(() => setT((Date.now() - start) / 1000), 1000)
    return () => clearInterval(id)
  }, [key])
  return t
}

function StepRow({ s, live }: { s: JobStep; live?: number }) {
  const Icon = { running: CircleNotch, done: Check, failed: X, cancelled: Minus }[s.status]
  return (
    <li className="grid grid-cols-[16px_minmax(0,1fr)_auto] items-start gap-x-3 py-1">
      <Icon size={13} weight="bold" className={cx('mt-[3px]', s.status === 'running' && 'text-ink motion-safe:animate-spin',
        s.status === 'done' && 'text-ok', s.status === 'failed' && 'text-danger', s.status === 'cancelled' && 'text-ink-3')} />
      <span className={cx('min-w-0', s.status === 'failed' ? 'text-ink' : s.status === 'running' ? 'text-ink' : 'text-ink-2')}>
        {s.step}
        {s.error && <span className="block text-danger">{s.error}</span>}
        {s.detail && (
          <details className="text-ink-3">
            <summary className="w-fit cursor-pointer select-none hover:text-ink">View technical details</summary>
            <pre data-selectable className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-2xs">{s.detail}</pre>
          </details>
        )}
      </span>
      <span className="tabular-nums text-ink-3">{secs(live ?? s.secs)}</span>
    </li>
  )
}

/** Live panel while a job runs: the current step and its elapsed time, the bar, and every step so far. */
export function JobProgress({ job, sectionRef }: { job: Job; sectionRef?: Ref<HTMLElement> }) {
  const log = shown(job.log ?? [])
  const current = log[log.length - 1]
  const elapsed = useElapsed(current ? `${log.length}:${current.step}` : '')
  const list = useRef<HTMLOListElement>(null)
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight }) }, [log.length])
  const failed = log.filter((s) => s.status === 'failed').length
  return (
    <section ref={sectionRef} aria-live="polite" className="glass mb-5 grid scroll-mt-6 gap-3 px-7 py-5">
      <div className="flex items-center justify-between gap-4 text-[13px]">
        <span className="text-ink">{job.stage || 'Starting'}</span>
        <span className="flex shrink-0 items-center gap-3">
          <span className="tabular-nums text-ink-3">{Math.round(job.progress * 100)}%</span>
          <Button variant="ghost" onClick={() => call('jobs.cancel', { id: job.id })}>Cancel</Button>
        </span>
      </div>
      <div className="h-0.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(job.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full origin-left bg-pop transition-transform duration-500 ease-out-expo" style={{ transform: `scaleX(${Math.max(job.progress, 0.02)})` }} />
      </div>
      {log.length > 1 && (
        <details open={failed > 0 || undefined} className="text-xs">
          <summary className="w-fit cursor-pointer select-none text-ink-3 hover:text-ink">
            Steps ({log.length}{failed ? `, ${failed} failed` : ''})
          </summary>
          <ol ref={list} className="mt-2 max-h-56 overflow-auto pr-2">
            {log.map((s, i) => <StepRow key={i} s={s} live={i === log.length - 1 && s.status === 'running' ? elapsed : undefined} />)}
          </ol>
        </details>
      )}
    </section>
  )
}

/** After a job: what ran, how long each step took and what failed. Opens by itself when something failed. */
export function JobLog({ job }: { job: Job }) {
  const log = shown(job.log ?? [])
  if (job.status === 'running' || job.status === 'queued' || log.length < 2) return null
  const failed = log.filter((s) => s.status === 'failed').length
  const total = log.reduce((a, s) => a + s.secs, 0)
  return (
    <details open={failed > 0 || undefined} className="glass mb-6 px-7 py-4 text-xs">
      <summary className="w-fit cursor-pointer select-none text-[13px] text-ink-2 hover:text-ink">
        What happened: {log.length} steps in {secs(total)}{failed ? `, ${failed} failed` : ''}
      </summary>
      <ol className="mt-3 max-h-72 overflow-auto pr-2">
        {log.map((s, i) => <StepRow key={i} s={s} />)}
      </ol>
    </details>
  )
}
