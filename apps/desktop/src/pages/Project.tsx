import type { CSSProperties } from 'react'
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, CalendarBlank, Export, PaperPlaneTilt, Play, Sparkle, Trash, X } from '@phosphor-icons/react'
import { call, formatDate, FORMATS, hasKey, label, PLATFORMS, useJob, useQuery, BackendError, startFailures,
  type Asset, type Piece, type Project as P, type Publication, type Render, type ScheduleItem } from '../lib/studio'
import { Preview } from '../components/Preview'
import { ClipWorkspace } from '../components/Clips'
import { Button, ErrorNote, cx, Reveal } from '../components/ui'
import { JobLog, JobProgress } from '../components/JobProgress'
import { Cover } from '../components/Cover'
import { FootageReview } from '../components/FootageReview'
import { PostDialog, PublicationChips, ScheduleAllDialog } from '../components/Posting'

const CANCELLED: Record<string, string> = {
  generate: 'Generation was cancelled.', render: 'Rendering was cancelled.', export: 'The export was cancelled.',
  clip: 'Clipping was cancelled.', visuals: 'The footage download was cancelled.',
  visuals_render: 'Download and render was cancelled.',
}

export function Project({ id, onBack, onSettings }: { id: string; onBack: () => void; onSettings: () => void }) {
  const { data: project, error: loadError, reload: reloadProject } = useQuery<P>('projects.get', { id })
  const { job, reload: reloadJob } = useJob(id)
  const running = job?.status === 'queued' || job?.status === 'running'
  const [rev, setRev] = useState(0)
  const { data: pieces } = useQuery<Piece[]>(
    'pieces.list', { project_id: id }, `${job?.status ?? ''}|${job?.stage ?? ''}|${rev}`)  // per step, not per progress tick
  const { data: renders } = useQuery<Render[]>(
    'renders.list', { project_id: id }, `${job?.status ?? ''}|${job?.stage ?? ''}|${rev}`)
  const { data: assets } = useQuery<Asset[]>('assets.list')
  const [preview, setPreview] = useState<string>()
  const [posting, setPosting] = useState<string>()
  const [scheduling, setScheduling] = useState(false)
  const { data: pubs, reload: reloadPubs } = useQuery<Publication[]>('publish.publications', { project_id: id }, rev)
  // while a post is waiting to go out, look again every minute so "Scheduled" turns into "Posted" by itself
  const pending = pubs?.some((p) => p.status === 'scheduled' || p.status === 'sending')
  useEffect(() => {
    if (!pending) return
    const t = window.setInterval(reloadPubs, 60_000)
    return () => window.clearInterval(t)
  }, [pending])
  const [keySet, setKeySet] = useState<boolean>()
  const [error, setError] = useState<BackendError | undefined>(() => {  // the first job may have failed to start
    const e = startFailures.get(id)
    startFailures.delete(id)
    return e
  })

  const refresh = () => setRev((r) => r + 1)  // piece-level changes (regenerate, delete) don't move any job timestamp

  // bring the finished pieces into view when a job completes (they render below the progress bar)
  const listRef = useRef<HTMLOListElement>(null)
  const reviewRef = useRef<HTMLDivElement>(null)
  const progressRef = useRef<HTMLElement>(null)
  // a job started from further down the page (Download and render) brings its progress bar into view
  useEffect(() => { if (running) progressRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }, [running])
  useEffect(() => {  // footage waiting for a pick is the next thing to do, so it wins the scroll over the list
    if (job?.status === 'completed') (reviewRef.current ?? listRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [job?.status, pieces?.some((p) => p.content.review)])

  useEffect(() => { hasKey('OPENROUTER_API_KEY').then(setKeySet) }, [])
  useEffect(() => { if (job && !running) reloadProject() }, [job?.status])

  const reviewing = pieces?.filter((p) => p.content.review) ?? []
  // "Schedule all": every rendered piece with nothing scheduled or posted yet (failed and cancelled posts don't count)
  const unscheduled: ScheduleItem[] = (pieces ?? []).filter((p) => ['ready', 'exported'].includes(p.status)
    && renders?.some((r) => r.piece_id === p.id)
    && !pubs?.some((x) => x.piece_id === p.id && x.status !== 'error' && x.status !== 'canceled'))
    .map((p) => ({ key: `piece:${p.id}`, title: p.content.quote.text, piece_id: p.id,
      video: !!renders?.some((r) => r.piece_id === p.id && r.kind === 'video'),
      cover: renders?.find((r) => r.piece_id === p.id && r.kind === 'image')?.local_path ?? null }))
  // footage waiting for the user's pick blocks rendering: nothing renders on footage nobody confirmed
  const renderable = !reviewing.length && !!pieces?.some((p) => p.status !== 'failed' && p.content.asset)

  async function generate() {
    if (running || !keySet) return
    if (pieces?.length && !confirm('Generate again? This replaces the pieces below with a new batch.')) return
    setError(undefined)
    try { await call('jobs.start', { project_id: id }); reloadJob() } catch (e) { setError(e as BackendError) }
  }

  // "Try again" repeats the job that failed. A failed render or export must never regenerate (rewrite) the batch.
  async function retry() {
    if (running || !job) return
    const kind = job.kind ?? 'generate'
    if (kind === 'generate') return generate()
    setError(undefined)
    try { await call('jobs.start', { project_id: id, kind }); reloadJob() } catch (e) { setError(e as BackendError) }
  }

  async function render() {
    if (running || !renderable) return
    setError(undefined)
    try { await call('jobs.start', { project_id: id, kind: 'render' }); reloadJob() } catch (e) { setError(e as BackendError) }
  }

  async function exportAll() {
    if (running) return
    setError(undefined)
    try { await call('jobs.start', { project_id: id, kind: 'export' }); reloadJob() } catch (e) { setError(e as BackendError) }
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
  if (project.brief.kind === 'clip') return <ClipWorkspace project={project} onBack={onBack} onSettings={onSettings} />
  const b = project.brief
  const meta = [label(b.tone), FORMATS.find((f) => f.value === b.format)!.label, `${b.quantity} ${b.quantity === 1 ? 'piece' : 'pieces'}`,
    b.platforms.map((p) => PLATFORMS.find((x) => x.value === p)!.label).join(', '), formatDate(project.created_at)]

  return (
    <>
      <header className="grid gap-4 pb-8">
        <div><Button variant="ghost" onClick={onBack} className="-ml-3"><ArrowLeft size={14} />Projects</Button></div>
        <div className="flex items-end justify-between gap-6">
          <div className="min-w-0">
            <h1 key={project.name} className="font-display text-title font-semibold tracking-[-0.03em]"><Reveal text={project.name} /></h1>
            <p className="anim-drift mt-1 text-[13px] text-ink-3" style={{ '--d': '200ms' } as CSSProperties}>{meta.join('  /  ')}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" onClick={remove} aria-label="Delete project"><Trash size={15} /></Button>
            {unscheduled.length > 0 && (
              <Button onClick={() => setScheduling(true)} disabled={running}
                title="Pick a date and time for every piece, then post them all in one go"><CalendarBlank size={14} />Schedule all</Button>
            )}
            {!!renders?.length && (
              <Button onClick={exportAll} disabled={running} title="Copy rendered pieces into an export folder">
                <Export size={14} />Export
              </Button>
            )}
            <Button onClick={render} disabled={running || !renderable}
              title={reviewing.length ? 'Choose the footage first' : renderable ? 'Narrate and render every piece' : 'Generate pieces with visuals first'}>
              <Play size={13} weight="fill" />Render
            </Button>
            <Button variant="primary" onClick={generate} disabled={running || !keySet} kbd="Ctrl Enter">
              <Sparkle size={14} weight="fill" />{pieces?.length ? 'Generate again' : 'Generate'}
            </Button>
          </div>
        </div>
      </header>

      {keySet === false && (
        <div className="mb-6"><ErrorNote error={{ message: 'Add your OpenRouter API key in Settings to generate content.' }}
          action={<Button onClick={onSettings}>Open Settings</Button>} /></div>
      )}
      {error && <div className="mb-6"><ErrorNote error={error} /></div>}

      {running && job && <JobProgress job={job} sectionRef={progressRef} />}
      {job?.status === 'failed' && job.error && !running && (
        <div className="mb-8"><ErrorNote error={job.error}
          action={(keySet || !['generate', 'clip'].includes(job.kind ?? 'generate')) && <Button onClick={retry}>Try again</Button>} /></div>
      )}
      {job?.status === 'cancelled' && <p className="mb-8 text-[13px] text-ink-3">{CANCELLED[job.kind ?? 'generate'] ?? 'Cancelled.'}</p>}
      {job && !running && <JobLog job={job} />}

      {pieces?.length === 0 && !running && (
        <section className="grid max-w-md gap-3 py-12">
          <h2 className="text-base font-semibold">Nothing generated yet</h2>
          <p className="text-ink-2">Generate writes {b.quantity === 1 ? 'one piece' : `${b.quantity} distinct pieces`} from this brief: {b.format === 'image' || b.format === 'image_voiced' ? 'a quote, a photo search' : 'a quote, spoken narration, a visual search'} and platform captions for each.</p>
        </section>
      )}

      {!!reviewing.length && !running && (
        <div ref={reviewRef} className="scroll-mt-6">
          <FootageReview key={reviewing.map((p) => p.id).join()} pieces={reviewing} onStarted={reloadJob} />
        </div>
      )}

      <ol ref={listRef} className={cx('grid', (!!pieces?.length || running) && 'glass px-8 py-2')}>
        {pieces?.map((p) => (
          <PieceRow key={p.id} piece={p} renders={renders?.filter((r) => r.piece_id === p.id)}
            pubs={pubs?.filter((x) => x.piece_id === p.id) ?? []} onPubsChanged={reloadPubs} onPost={() => setPosting(p.id)}
            onPreview={() => setPreview(p.id)} busy={running} onChanged={refresh} onError={setError} />
        ))}
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
      {pieces?.filter((p) => p.id === posting).map((p) => (
        <PostDialog key={p.id} title={p.content.quote.text} kind={renders?.some((r) => r.piece_id === p.id && r.kind === 'video') ? 'video' : 'image'}
          video={!!renders?.some((r) => r.piece_id === p.id && r.kind === 'video')}
          onClose={() => setPosting(undefined)} onDone={reloadPubs} onSettings={onSettings}
          send={(account_ids, due_at) => call<Publication[]>('publish.zernio_publish_piece', { piece_id: p.id, account_ids, due_at })} />
      ))}
      {scheduling && <ScheduleAllDialog projectId={id} items={unscheduled} onClose={() => setScheduling(false)}
        onDone={reloadPubs} onSettings={onSettings} />}
      {pieces?.length ? pieces.filter((p) => p.id === preview).map((p) => (
        <Preview key={p.id} piece={p} renders={renders?.filter((r) => r.piece_id === p.id) ?? []} assets={assets ?? []}
          voice={b.voice} onClose={() => setPreview(undefined)} onChanged={refresh} />
      )) : null}
    </>
  )
}

function PieceRow({ piece: p, renders, pubs, onPubsChanged, onPost, onPreview, busy, onChanged, onError }: {
  piece: Piece; renders?: Render[]; pubs: Publication[]; onPubsChanged: () => void; onPost: () => void
  onPreview: () => void; busy?: boolean; onChanged: () => void; onError: (e: BackendError) => void
}) {
  const c = p.content
  const tag = String(p.idx).padStart(3, '0')
  const [renewing, setRenewing] = useState(false)
  async function drop(method: string, params: object, question: string) {
    if (!confirm(question)) return
    try { await call(method, params); onChanged() } catch (e) { onError(e as BackendError) }
  }
  const deletePiece = (
    <Button variant="ghost" className="!px-2" disabled={busy} aria-label={`Delete piece ${tag}`}
      title="Delete this piece and its renders"
      onClick={() => drop('pieces.delete', { piece_id: p.id }, `Delete piece ${tag} and its renders? This can't be undone.`)}>
      <Trash size={13} />
    </Button>
  )
  const image = renders?.find((r) => r.kind === 'image')?.local_path
  if (p.status === 'failed') {
    return (
      <li className="grid grid-cols-[56px_minmax(0,1fr)] gap-6 border-t border-line py-7 first:border-t-0">
        <span className="tnum pt-1 text-xs text-ink-3">{String(p.idx).padStart(3, '0')}</span>
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-1">
            <p className="text-[13px] text-ink-2">{p.angle}</p>
            <p className="text-[13px] text-danger">{c.error}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {c.error?.startsWith("This quote couldn't be confirmed") && (  // the fact check failed it: a new quote fixes it
              <Button disabled={busy || renewing} onClick={async () => {
                setRenewing(true)
                try { await call('pieces.regenerate', { piece_id: p.id, scope: 'quote' }); onChanged() }
                catch (e) { onError(e as BackendError) } finally { setRenewing(false) }
              }}>{renewing ? 'Writing…' : 'New quote'}</Button>
            )}
            {deletePiece}
          </div>
        </div>
      </li>
    )
  }
  return (
    <li className="anim-slot grid grid-cols-[56px_minmax(0,1fr)_172px] gap-6 border-t border-line py-7 first:border-t-0 max-[1100px]:grid-cols-[56px_minmax(0,1fr)]">
      <span className="tnum pt-2 font-display text-xs text-accent-ink">{String(p.idx).padStart(3, '0')}</span>
      <div className="grid gap-4">
        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-ink-3">{label(p.angle)}</p>
            <div className="flex shrink-0 items-center gap-1.5">
              {p.status !== 'written' && p.status !== 'rendering' && (
                <span className={cx('rounded-full px-2.5 py-0.5 text-2xs font-medium',
                  p.status === 'ready' ? 'bg-black/[0.07] text-ink-2' : 'bg-ok/15 text-ok')}>{label(p.status)}</span>
              )}
              {!!renders?.length && (
                <>
                  {renders.map((r) => (
                    <span key={r.id} className="group/chip inline-flex items-center rounded-full bg-accent/15 text-2xs font-medium text-accent-ink">
                      <button onClick={onPreview} title={r.local_path}
                        className="inline-flex items-center gap-1 rounded-full py-0.5 pl-2.5 pr-1.5 hover:text-ink">
                        {r.kind === 'video' ? <Play size={8} weight="fill" /> : null}
                        {label(r.kind)}{r.duration ? ` ${r.duration.toFixed(1)}s` : ''}
                      </button>
                      <button disabled={busy} aria-label={`Delete the ${r.kind} render of piece ${tag}`}
                        onClick={() => drop('renders.delete', { render_id: r.id }, `Delete the ${r.kind} render of piece ${tag}? You can render it again.`)}
                        className="mr-1 grid size-4 place-items-center rounded-full opacity-60 hover:bg-accent/30 hover:opacity-100 disabled:opacity-30">
                        <X size={9} weight="bold" />
                      </button>
                    </span>
                  ))}
                  <Button variant="ghost" className="!px-2 !text-xs" onClick={onPreview}>Preview</Button>
                  <Button variant="ghost" className="!px-2 !text-xs" disabled={busy} onClick={onPost}
                    title="Post or schedule this to your social accounts"><PaperPlaneTilt size={13} />Post</Button>
                </>
              )}
              {deletePiece}
            </div>
          </div>
          <blockquote data-selectable className="max-w-[34ch] font-display text-[24px] leading-[1.25] font-semibold tracking-[-0.025em] text-balance">
            {c.quote.text}
          </blockquote>
          <PublicationChips rows={pubs} onChanged={onPubsChanged} />
        </div>
        {c.narration && <p data-selectable className="max-w-[68ch] text-[13px] leading-relaxed text-ink-2">{c.narration.text}</p>}
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-1.5 text-xs">
          <dt className="text-ink-3">Visual</dt>
          <dd data-selectable className="text-ink-2">{label(c.visual.preferred_type)}: {c.visual.search_query}</dd>
          {c.visual_error && (<>
            <dt className="text-ink-3">Asset</dt>
            <dd className="text-danger">{c.visual_error}</dd>
          </>)}
          {c.render_error && (<>
            <dt className="text-ink-3">Render</dt>
            <dd className="text-danger">{c.render_error}
              {c.render_error_detail && (
                <details className="text-ink-3">
                  <summary className="w-fit cursor-pointer select-none hover:text-ink">View technical details</summary>
                  <pre data-selectable className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-2xs">{c.render_error_detail}</pre>
                </details>
              )}
            </dd>
          </>)}
          {c.narration && c.design && (<>
            <dt className="text-ink-3">Delivery</dt>
            <dd className="text-ink-2">{label(c.narration.delivery.replace('_', ' '))}, {c.design.composition} composition, {c.design.animation} motion</dd>
          </>)}
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
      {/* the piece's face: its rendered 4:5 once it exists (click to preview), its line on a frame until then */}
      <button onClick={onPreview} disabled={!renders?.length} aria-label={renders?.length ? 'Preview this piece' : undefined}
        className="group self-start rounded-[18px] disabled:cursor-default max-[1100px]:hidden">
        <Cover src={image} quote={c.quote.text} className="transition-transform duration-300 ease-[var(--ease-premium)] group-enabled:group-hover:-translate-y-1" />
      </button>
    </li>
  )
}
