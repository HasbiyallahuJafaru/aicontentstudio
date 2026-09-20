// Clip project workspace: the review list for a clipped video (scored moments, karaoke-captioned shorts)
// with approve/reject, a preview modal and export — riding the same job system as the other kinds.
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Check, Export, PaperPlaneTilt, Play, Trash, X } from '@phosphor-icons/react'
import { call, formatDate, hasKey, label, mediaUrl, useJob, useQuery, BackendError,
  type BufferChannel, type Clip, type Project as P } from '../lib/studio'
import { Button, Dialog, ErrorNote, Field, Input, cx } from './ui'

const POST_ORDER = ['tiktok', 'instagram', 'youtube', 'linkedin', 'facebook', 'x'] as const

export function ClipWorkspace({ project, onBack, onSettings }: { project: P; onBack: () => void; onSettings: () => void }) {
  const { job, reload: reloadJob } = useJob(project.id)
  const running = job?.status === 'queued' || job?.status === 'running'
  const [rev, setRev] = useState(0)
  const { data: clips } = useQuery<Clip[]>('clips.list', { project_id: project.id }, `${job?.updated_at ?? ''}|${rev}`)
  const [preview, setPreview] = useState<string>()
  const [publishing, setPublishing] = useState<Clip>()
  const [error, setError] = useState<BackendError>()
  const [keys, setKeys] = useState<Record<string, boolean>>()

  useEffect(() => {
    Promise.all([hasKey('GROQ_API_KEY'), hasKey('DEEPSEEK_API_KEY')])
      .then(([groq, deepseek]) => setKeys({ groq, deepseek }))
  }, [])
  useEffect(() => { if (job && !running) setRev((r) => r + 1) }, [job?.status])

  const b = project.brief.kind === 'clip' ? project.brief : null
  if (!b) return null

  const ready = clips?.filter((c) => c.video_path && c.status !== 'rejected') ?? []

  async function start(kind: 'clip' | 'export') {
    if (running) return
    setError(undefined)
    try { await call('jobs.start', { project_id: project.id, kind }); reloadJob() } catch (e) { setError(e as BackendError) }
  }

  async function remove() {
    if (!confirm(`Delete "${project.name}" and its clips? This can't be undone.`)) return
    try { await call('projects.delete', { id: project.id }); onBack() } catch (e) { setError(e as BackendError) }
  }

  const review = async (id: string, status: string) => {
    setError(undefined)
    try { await call('clips.review', { id, status }); setRev((r) => r + 1) } catch (e) { setError(e as BackendError) }
  }

  // bring the finished clips into view when the job completes
  const listRef = useRef<HTMLOListElement>(null)
  useEffect(() => {
    if (job?.status === 'completed') listRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [job?.status])

  return (
    <>
      <header className="grid gap-4 pb-8">
        <div><Button variant="ghost" onClick={onBack} className="-ml-3"><ArrowLeft size={14} />Projects</Button></div>
        <div className="flex items-end justify-between gap-6">
          <div className="min-w-0">
            <h1 className="font-display text-title font-semibold tracking-[-0.03em]">{project.name}</h1>
            <p className="mt-1 truncate text-[13px] text-ink-3">{b.source}</p>
            <p className="text-[13px] text-ink-3">{b.orientation} · clips {b.min_len}-{b.max_len}s
              {b.n ? ` · ${b.n} wanted` : ' · auto count'} · {formatDate(project.created_at)}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" onClick={remove} aria-label="Delete project"><Trash size={15} /></Button>
            {!!ready.length && (
              <Button onClick={() => start('export')} disabled={running}><Export size={14} />Export</Button>
            )}
            <Button variant="primary" onClick={() => start('clip')} disabled={running}
              title={clips?.length ? 'Clip this video again from scratch' : 'Transcribe, pick moments and render clips'}>
              <Play size={13} weight="fill" />{clips?.length ? 'Clip again' : 'Clip'}
            </Button>
          </div>
        </div>
      </header>

      {keys && (keys.groq === false || keys.deepseek === false) && (
        <div className="mb-6"><ErrorNote error={{ message: 'Clipping needs a Groq key (transcription) and a DeepSeek key (selection). Add them in Settings.' }}
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
        <div className="mb-8"><ErrorNote error={job.error} action={<Button onClick={() => start('clip')}>Try again</Button>} /></div>
      )}
      {job?.status === 'cancelled' && <p className="mb-8 text-[13px] text-ink-3">Clipping was cancelled.</p>}

      {!clips?.length && !running && (
        <section className="grid max-w-md gap-3 py-12">
          <h2 className="text-base font-semibold">No clips yet</h2>
          <p className="text-ink-2">Clipping downloads the video, transcribes it with Groq, asks DeepSeek to pick the
            moments that stand alone, then renders face-framed {b.orientation} clips with karaoke captions.</p>
        </section>
      )}

      {!!clips?.length && (
        <ol ref={listRef} className="glass px-8 py-2">
          {clips.map((c) => (
            <ClipRow key={c.id} clip={c} onPreview={() => setPreview(c.id)} onPublish={() => setPublishing(c)}
              onReview={(status) => review(c.id, status)} busy={running} />
          ))}
        </ol>
      )}
      {clips?.filter((c) => c.id === preview).map((c) => (
        <ClipPreview key={c.id} clip={c} onClose={() => setPreview(undefined)} onPublish={() => setPublishing(c)} />
      ))}
      {clips?.filter((c) => c.id === publishing?.id).map((c) => (
        <PublishDialog key={c.id} clip={c} onClose={() => setPublishing(undefined)}
          onChanged={() => { setPublishing(undefined); setRev((r) => r + 1) }} />
      ))}
    </>
  )
}

function ClipRow({ clip: c, onPreview, onPublish, onReview, busy }: {
  clip: Clip; onPreview: () => void; onPublish: () => void
  onReview: (status: 'approved' | 'ready' | 'rejected') => void; busy: boolean
}) {
  return (
    <li className="anim-slot grid grid-cols-[56px_72px_minmax(0,1fr)_auto] items-center gap-6 border-t border-line py-5 first:border-t-0 max-[900px]:grid-cols-[40px_56px_minmax(0,1fr)_auto]">
      <span className="tnum font-display text-xs text-accent">{String(c.idx).padStart(2, '0')}</span>
      <button onClick={onPreview} className="overflow-hidden rounded-[8px] bg-black/30 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1)]"
        aria-label={`Preview clip ${c.idx}`}>
        <img src={mediaUrl(c.cover_path)} alt="" className="aspect-video w-full object-cover" />
      </button>
      <div className="grid gap-1">
        <p className="flex items-baseline gap-2.5">
          <span data-selectable className="font-display text-[17px] font-semibold tracking-[-0.02em]">{c.title}</span>
          <span className="tnum shrink-0 rounded-full bg-accent/15 px-2 py-0.5 text-2xs font-medium text-accent">{c.score}</span>
          <span className="tnum shrink-0 text-2xs text-ink-3">{(c.end_at - c.start_at).toFixed(0)}s</span>
        </p>
        <p data-selectable className="line-clamp-1 text-[13px] text-ink-2">{c.hook}</p>
        {c.status !== 'ready' && (
          <span className={cx('w-fit rounded-full px-2.5 py-0.5 text-2xs font-medium',
            c.status === 'rejected' ? 'bg-danger/15 text-danger' : 'bg-ok/15 text-ok')}>{label(c.status)}</span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {c.status === 'approved' && (
          <Button variant="ghost" disabled={busy} onClick={onPublish}><PaperPlaneTilt size={13} />Publish</Button>
        )}
        {c.status === 'approved'
          ? <Button variant="ghost" disabled={busy} onClick={() => onReview('ready')}>Unapprove</Button>
          : <Button variant="ghost" disabled={busy} onClick={() => onReview('approved')}><Check size={13} weight="bold" />Approve</Button>}
        {c.status === 'rejected'
          ? <Button variant="ghost" disabled={busy} onClick={() => onReview('ready')}>Restore</Button>
          : <Button variant="ghost" disabled={busy} onClick={() => onReview('rejected')}><X size={13} />Reject</Button>}
        <Button variant="ghost" className="!px-2 !text-xs" onClick={onPreview}>Preview</Button>
      </div>
    </li>
  )
}

// Two columns: the clip fills the panel height on the left, everything readable or clickable sits in
// the right rail. Only the rail's middle band scrolls, so the publish button is never below the fold.
function ClipPreview({ clip: c, onClose, onPublish }: { clip: Clip; onClose: () => void; onPublish: () => void }) {
  return (
    <Dialog label={`Preview clip ${c.idx}`} width={1180} onClose={onClose}
      className="h-[min(780px,calc(100dvh-3rem))] grid-cols-[minmax(0,1fr)_368px] max-[1040px]:h-[calc(100dvh-3rem)] max-[1040px]:grid-cols-1 max-[1040px]:grid-rows-[minmax(0,1fr)_auto]">
      <section className="grid min-h-0 place-items-center p-3">
        <video src={mediaUrl(c.video_path)} controls className="max-h-full max-w-full rounded-field bg-black/35" />
      </section>

      <aside className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] border-l border-line max-[1040px]:border-l-0 max-[1040px]:border-t">
        <header className="grid gap-2 border-b border-line px-6 py-5">
          <div className="flex items-start justify-between gap-3">
            <p className="tnum text-xs text-ink-3">Clip {String(c.idx).padStart(2, '0')} · {(c.end_at - c.start_at).toFixed(0)}s · score {c.score}</p>
            <Button variant="ghost" onClick={onClose} aria-label="Close preview" className="-mt-2 -mr-3 h-8"><X size={15} /></Button>
          </div>
          <h2 className="line-clamp-3 font-display text-[17px] font-semibold leading-snug tracking-[-0.02em]">{c.title}</h2>
          <span className={cx('w-fit rounded-full px-3 py-1 text-2xs font-medium',
            c.status === 'rejected' ? 'bg-danger/15 text-danger' : 'bg-white/[0.07] text-ink-2')}>{label(c.status)}</span>
        </header>

        <div className="grid content-start gap-4 overflow-y-auto px-6 py-5 text-[13px]">
          <div className="grid gap-1">
            <p className="text-ink-3">Hook</p>
            <p data-selectable className="text-ink">{c.hook}</p>
          </div>
          <div className="grid gap-1">
            <p className="text-ink-3">Description</p>
            <p data-selectable className="text-ink-2">{c.description}</p>
          </div>
          <div className="grid gap-1">
            <p className="text-ink-3">Why this moment</p>
            <p data-selectable className="text-ink-2">{c.reason}</p>
          </div>
          <details className="text-xs">
            <summary className="w-fit cursor-pointer list-none text-ink-3 hover:text-ink">Post copy per platform</summary>
            <dl data-selectable className="mt-3 grid grid-cols-[76px_minmax(0,1fr)] gap-x-4 gap-y-2 text-ink-2">
              {POST_ORDER.filter((n) => c.posts[n]).map((n) => (
                <div key={n} className="col-span-2 grid grid-cols-subgrid">
                  <dt className="text-ink-3">{label(n)}</dt>
                  <dd className="whitespace-pre-line">{c.posts[n]}</dd>
                </div>
              ))}
              <div className="col-span-2 grid grid-cols-subgrid">
                <dt className="text-ink-3">Hashtags</dt>
                <dd>{c.hashtags.join(' ')}</dd>
              </div>
            </dl>
          </details>
        </div>

        {c.status === 'approved' && (
          <div className="flex justify-end border-t border-line px-6 py-4">
            <Button variant="primary" onClick={onPublish}><PaperPlaneTilt size={14} />Publish</Button>
          </div>
        )}
      </aside>
    </Dialog>
  )
}

function PublishDialog({ clip: c, onClose, onChanged }: {
  clip: Clip; onClose: () => void; onChanged: () => void
}) {
  const { data: channels, error: channelsError } = useQuery<BufferChannel[]>('publish.buffer_channels')
  const [picked, setPicked] = useState<string[]>([])
  const [when, setWhen] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error>()

  async function publish() {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      await call('publish.buffer_publish', { project_id: c.project_id, clip_idx: c.idx, channel_ids: picked,
        due_at: when ? new Date(when).toISOString() : undefined })
      onChanged()
      onClose()
    } catch (e) {
      setError(e as Error)
      setBusy(false)
    }
  }

  const usable = channels?.filter((ch) => ch.usable) ?? []
  return (
    <Dialog label={`Publish clip ${c.idx}`} width={560} onClose={onClose} className="grid-rows-[auto_minmax(0,1fr)_auto]">
      <header className="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
        <div>
          <p className="text-xs text-ink-3">Publish to Buffer</p>
          <h2 className="mt-0.5 font-display text-[18px] font-semibold tracking-[-0.02em]">{c.title}</h2>
        </div>
        <Button variant="ghost" onClick={onClose} aria-label="Close" className="-mt-2 -mr-3 h-8"><X size={15} /></Button>
      </header>

      <div className="grid content-start gap-5 overflow-y-auto px-6 py-5">
        {channelsError && <ErrorNote error={channelsError} />}
        {channels && usable.length === 0 && !channelsError && (
          <p className="text-[13px] text-ink-2">No usable channels in Buffer. Connect a network inside Buffer first.</p>
        )}
        <fieldset className="grid gap-1.5">
          <legend className="mb-1.5 text-[13px] font-medium text-ink">Channels</legend>
          {usable.map((ch) => (
            <button key={ch.id} type="button"
              onClick={() => setPicked(picked.includes(ch.id) ? picked.filter((x) => x !== ch.id) : [...picked, ch.id])}
              className={cx('flex items-center justify-between rounded-[10px] px-3.5 py-2.5 text-left text-[13px] transition-colors duration-150',
                picked.includes(ch.id) ? 'bg-white/[0.08] text-ink' : 'text-ink-2 hover:bg-white/[0.05]')}>
              {ch.displayName || ch.name}
              <span className="text-2xs uppercase tracking-wide text-ink-3">{ch.service}</span>
            </button>
          ))}
        </fieldset>

        <Field label="Schedule" hint="Leave empty to post now. Buffer can also reschedule it later.">
          {(id) => <Input id={id} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />}
        </Field>

        {error && <ErrorNote error={error} />}
      </div>

      <div className="flex justify-end gap-2 border-t border-line px-6 py-4">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!picked.length || busy} onClick={publish}>
          <PaperPlaneTilt size={14} />{busy ? 'Publishing…' : when ? 'Schedule' : 'Post now'}
        </Button>
      </div>
    </Dialog>
  )
}
