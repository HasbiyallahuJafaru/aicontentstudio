import { useEffect, useState } from 'react'
import { ArrowLeft, Sparkle, Trash } from '@phosphor-icons/react'
import { call, formatDate, FORMATS, hasKey, label, PLATFORMS, useJob, useQuery, BackendError, type Piece, type Project as P } from '../lib/studio'
import { Button, ErrorNote, cx } from '../components/ui'

export function Project({ id, onBack, onSettings }: { id: string; onBack: () => void; onSettings: () => void }) {
  const { data: project, error: loadError, reload: reloadProject } = useQuery<P>('projects.get', { id })
  const { job, reload: reloadJob } = useJob(id)
  const running = job?.status === 'queued' || job?.status === 'running'
  const { data: pieces } = useQuery<Piece[]>('pieces.list', { project_id: id }, job?.updated_at)
  const [keySet, setKeySet] = useState<boolean>()
  const [error, setError] = useState<BackendError>()

  useEffect(() => { hasKey('DEEPSEEK_API_KEY').then(setKeySet) }, [])
  useEffect(() => { if (job && !running) reloadProject() }, [job?.status])

  async function generate() {
    if (running || !keySet) return
    if (pieces?.length && !confirm('Generate again? This replaces the pieces below with a new batch.')) return
    setError(undefined)
    try { await call('jobs.start', { project_id: id }); reloadJob() } catch (e) { setError(e as BackendError) }
  }

  async function remove() {
    if (!project || !confirm(`Delete "${project.name}" and everything generated for it? This can't be undone.`)) return
    try { await call('projects.delete', { id }); onBack() } catch (e) { setError(e as BackendError) }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') generate() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (loadError) return <ErrorNote error={loadError} action={<Button onClick={onBack}>Back to projects</Button>} />
  if (!project) return null
  const b = project.brief
  const meta = [label(b.tone), FORMATS.find((f) => f.value === b.format)!.label, `${b.quantity} ${b.quantity === 1 ? 'piece' : 'pieces'}`,
    b.platforms.map((p) => PLATFORMS.find((x) => x.value === p)!.label).join(', '), formatDate(project.created_at)]

  return (
    <>
      <header className="grid gap-4 pb-8">
        <div><Button variant="ghost" onClick={onBack} className="-ml-3"><ArrowLeft size={14} />Projects</Button></div>
        <div className="flex items-end justify-between gap-6">
          <div className="min-w-0">
            <h1 className="font-display text-title font-semibold tracking-[-0.03em]">{project.name}</h1>
            <p className="mt-1 text-[13px] text-ink-3">{meta.join('  /  ')}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" onClick={remove} aria-label="Delete project"><Trash size={15} /></Button>
            <Button variant="primary" onClick={generate} disabled={running || !keySet} kbd="Ctrl Enter">
              <Sparkle size={14} weight="fill" />{pieces?.length ? 'Generate again' : 'Generate'}
            </Button>
          </div>
        </div>
      </header>

      {keySet === false && (
        <div className="mb-6"><ErrorNote error={{ message: 'Add your DeepSeek API key in Settings to generate content.' }}
          action={<Button onClick={onSettings}>Open Settings</Button>} /></div>
      )}
      {error && <div className="mb-6"><ErrorNote error={error} /></div>}

      {running && job && (
        <section aria-live="polite" className="glass mb-5 grid gap-3 px-7 py-5">
          <div className="flex items-center justify-between gap-4 text-[13px]">
            <span className="text-ink">{job.stage || 'Starting'}</span>
            <Button variant="ghost" onClick={() => call('jobs.cancel', { id: job.id })}>Cancel</Button>
          </div>
          <div className="h-0.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(job.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full origin-left bg-accent transition-transform duration-500 ease-out-expo" style={{ transform: `scaleX(${Math.max(job.progress, 0.02)})` }} />
          </div>
        </section>
      )}
      {job?.status === 'failed' && job.error && !running && (
        <div className="mb-8"><ErrorNote error={job.error} action={keySet && <Button onClick={generate}>Try again</Button>} /></div>
      )}
      {job?.status === 'cancelled' && <p className="mb-8 text-[13px] text-ink-3">Generation was cancelled.</p>}

      {pieces?.length === 0 && !running && (
        <section className="grid max-w-md gap-3 py-12">
          <h2 className="text-base font-semibold">Nothing generated yet</h2>
          <p className="text-ink-2">Generate writes {b.quantity === 1 ? 'one piece' : `${b.quantity} distinct pieces`} from this brief: a quote, spoken narration, a visual search and platform captions for each.</p>
        </section>
      )}

      <ol className={cx('grid', (!!pieces?.length || running) && 'glass px-8 py-2')}>
        {pieces?.map((p) => <PieceRow key={p.id} piece={p} />)}
        {running && (pieces?.length ?? 0) < b.quantity && job?.stage.startsWith('Writing') && (
          <li className="grid grid-cols-[56px_minmax(0,1fr)] gap-6 border-t border-line py-7 first:border-t-0" aria-hidden>
            <span className="tnum pt-1 text-xs text-ink-3">{String((pieces?.length ?? 0) + 1).padStart(3, '0')}</span>
            <div className="grid gap-3">
              <div className="h-5 w-3/5 animate-pulse rounded bg-raised" />
              <div className="h-3.5 w-4/5 animate-pulse rounded bg-raised/70" />
            </div>
          </li>
        )}
      </ol>
    </>
  )
}

function PieceRow({ piece: p }: { piece: Piece }) {
  const c = p.content
  if (p.status === 'failed') {
    return (
      <li className="grid grid-cols-[56px_minmax(0,1fr)] gap-6 border-t border-line py-7 first:border-t-0">
        <span className="tnum pt-1 text-xs text-ink-3">{String(p.idx).padStart(3, '0')}</span>
        <div className="grid gap-1">
          <p className="text-[13px] text-ink-2">{p.angle}</p>
          <p className="text-[13px] text-danger">{c.error}</p>
        </div>
      </li>
    )
  }
  return (
    <li className="anim-slot grid grid-cols-[56px_minmax(0,1fr)] gap-6 border-t border-line py-7 first:border-t-0">
      <span className="tnum pt-2 font-display text-xs text-accent">{String(p.idx).padStart(3, '0')}</span>
      <div className="grid gap-4">
        <div className="grid gap-2">
          <p className="text-xs text-ink-3">{label(p.angle)}</p>
          <blockquote data-selectable className="max-w-[34ch] font-display text-[24px] leading-[1.25] font-semibold tracking-[-0.025em] text-balance">
            {c.quote.text}
          </blockquote>
        </div>
        <p data-selectable className="max-w-[68ch] text-[13px] leading-relaxed text-ink-2">{c.narration.text}</p>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-1.5 text-xs">
          <dt className="text-ink-3">Visual</dt>
          <dd data-selectable className="text-ink-2">{label(c.visual.preferred_type)}: {c.visual.search_query}</dd>
          {c.visual_error && (<>
            <dt className="text-ink-3">Asset</dt>
            <dd className="text-danger">{c.visual_error}</dd>
          </>)}
          <dt className="text-ink-3">Delivery</dt>
          <dd className="text-ink-2">{label(c.narration.delivery.replace('_', ' '))}, {c.design.composition} composition, {c.design.animation} motion</dd>
        </dl>
        <details className="group text-xs">
          <summary className="w-fit cursor-pointer list-none text-ink-3 hover:text-ink">Captions and metadata</summary>
          <dl data-selectable className="mt-3 grid max-w-[68ch] grid-cols-[88px_minmax(0,1fr)] gap-x-5 gap-y-2 text-ink-2">
            <dt className="text-ink-3">Title</dt><dd>{c.metadata.title}</dd>
            <dt className="text-ink-3">Caption</dt><dd className="whitespace-pre-line">{c.metadata.caption}</dd>
            <dt className="text-ink-3">Description</dt><dd>{c.metadata.description}</dd>
            <dt className="text-ink-3">Hashtags</dt><dd>{c.metadata.hashtags.join(' ')}</dd>
            <dt className="text-ink-3">Keywords</dt><dd>{c.metadata.keywords.join(', ')}</dd>
            <dt className="text-ink-3">Alt text</dt><dd>{c.metadata.alt_text}</dd>
          </dl>
        </details>
      </div>
    </li>
  )
}
