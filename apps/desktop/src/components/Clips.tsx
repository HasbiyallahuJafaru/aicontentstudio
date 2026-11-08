// Clip project workspace: the review list for a clipped video (scored moments, karaoke-captioned shorts)
// with approve/reject, a preview modal and export — riding the same job system as the other kinds.
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, CalendarBlank, Check, Copy, Export, PaperPlaneTilt, PencilSimple, Play, Trash, X } from '@phosphor-icons/react'
import { call, formatDate, hasKey, label, mediaUrl, useJob, useQuery, BackendError,
  type CalendarPlan, type Clip, type Project as P, type Publication } from '../lib/studio'
import { Button, Choices, Dialog, ErrorNote, Field, Input, Select, Textarea, cx } from './ui'
import { PostDialog, PublicationChips, SetUpPosting, ZernioPicker, useZernio } from './Posting'

const POST_ORDER = ['tiktok', 'instagram', 'youtube', 'linkedin', 'facebook', 'x'] as const
type Net = (typeof POST_ORDER)[number]
const NET_NAME: Record<Net, string> = { tiktok: 'TikTok', instagram: 'Instagram', youtube: 'YouTube', linkedin: 'LinkedIn', facebook: 'Facebook', x: 'X' }
// each network's caption limit (YouTube: the description), so an over-long post shows before it fails to publish
const NET_LIMIT: Record<Net, number> = { tiktok: 4000, instagram: 2200, youtube: 5000, linkedin: 3000, facebook: 63206, x: 280 }

/** The written post for one network at a time: tabs, the copy itself, its length against that network's limit,
 *  a copy button, and the hashtags as chips. */
function PostCopy({ clip: c }: { clip: Clip }) {
  const nets = POST_ORDER.filter((n) => c.posts[n])
  const [tab, setTab] = useState<Net | undefined>(nets[0])
  const [copied, setCopied] = useState(false)
  if (!tab) return null
  const text = c.posts[tab] ?? ''
  const over = text.length > NET_LIMIT[tab]
  async function copy() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }
  return (
    <section className="grid gap-3">
      <h3 className="text-xs text-ink-3">Post copy</h3>
      <div role="tablist" aria-label="Network" className="flex flex-wrap gap-1.5">
        {nets.map((n) => (
          <button key={n} type="button" role="tab" aria-selected={n === tab} onClick={() => { setTab(n); setCopied(false) }}
            className={cx('rounded-full px-3 py-1.5 text-xs font-medium transition-colors duration-150 active:scale-[0.97]',
              n === tab ? 'chip-on' : 'text-ink-2 shadow-[inset_0_0_0_1px_var(--color-line)] hover:bg-black/[0.04] hover:text-ink')}>
            {NET_NAME[n]}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={`${NET_NAME[tab]} post`} className="grid gap-3 rounded-field bg-ground p-4">
        <p data-selectable className="max-h-56 overflow-y-auto whitespace-pre-line leading-relaxed text-ink">{text}</p>
        <div className="flex items-center justify-between gap-3 border-t border-line pt-3">
          <span className={cx('tnum text-2xs', over ? 'text-danger' : 'text-ink-3')}>
            {text.length.toLocaleString()} / {NET_LIMIT[tab].toLocaleString()} characters{over && `, too long for ${NET_NAME[tab]}`}
          </span>
          <Button variant="ghost" onClick={copy} className="-mr-2 h-8">
            {copied ? <><Check size={13} weight="bold" />Copied</> : <><Copy size={13} />Copy</>}
          </Button>
        </div>
      </div>
      {c.hashtags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {c.hashtags.map((h) => (
            <span key={h} className="rounded-full bg-black/[0.05] px-2.5 py-1 text-2xs text-ink-2">{h.startsWith('#') ? h : `#${h}`}</span>
          ))}
        </div>
      )}
    </section>
  )
}

export function ClipWorkspace({ project, onBack, onSettings }: { project: P; onBack: () => void; onSettings: () => void }) {
  const { job, reload: reloadJob } = useJob(project.id)
  const running = job?.status === 'queued' || job?.status === 'running'
  const [rev, setRev] = useState(0)
  const { data: clips } = useQuery<Clip[]>('clips.list', { project_id: project.id }, `${job?.updated_at ?? ''}|${rev}`)
  const [preview, setPreview] = useState<string>()
  const [publishing, setPublishing] = useState<Clip>()
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState<BackendError>()
  const [keySet, setKeySet] = useState<boolean>()

  const { data: pubs, reload: reloadPubs } = useQuery<Publication[]>('publish.publications', { project_id: project.id }, rev)
  // while anything is still waiting to go out, look again every minute so "Scheduled" turns into "Posted" by itself
  const pending = pubs?.some((p) => p.status === 'scheduled' || p.status === 'sending')
  useEffect(() => {
    if (!pending) return
    const t = window.setInterval(reloadPubs, 60_000)
    return () => window.clearInterval(t)
  }, [pending])

  useEffect(() => { hasKey('OPENROUTER_API_KEY').then(setKeySet) }, [])
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

  const removeClip = async (c: Clip) => {
    if (!confirm(`Delete clip ${String(c.idx).padStart(2, '0')} "${c.title}"? Its video, cover and captions are removed from disk.`)) return
    setError(undefined)
    try { await call('clips.delete', { clip_id: c.id }); setRev((r) => r + 1) } catch (e) { setError(e as BackendError) }
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
          <div className="flex min-w-0 items-end gap-5">
          {b.thumb && <img src={mediaUrl(b.thumb)} alt="" className="aspect-video h-[72px] shrink-0 rounded-[10px] object-cover shadow-[inset_0_0_0_1px_rgb(17_18_20/0.1)]" />}
          <div className="min-w-0">
            <h1 className="font-display text-title font-semibold tracking-[-0.03em]">{project.name}</h1>
            <p className="mt-1 truncate text-[13px] text-ink-3">{b.source}</p>
            <p className="text-[13px] text-ink-3">{b.orientation} · clips {b.min_len}-{b.max_len}s
              {b.n ? ` · ${b.n} wanted` : ' · auto count'} · {formatDate(project.created_at)}</p>
          </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" onClick={remove} aria-label="Delete project"><Trash size={15} /></Button>
            {clips?.some((c) => c.status === 'approved') && (
              <Button variant="ghost" onClick={() => setPlanning(true)} disabled={running}
                title="Spread every approved clip over posting days and times"><CalendarBlank size={14} />Plan calendar</Button>
            )}
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

      {keySet === false && (
        <div className="mb-6"><ErrorNote error={{ message: 'Clipping needs your OpenRouter API key. Add it in Settings.' }}
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
            <div className="h-full origin-left bg-pop transition-transform duration-500 ease-out-expo" style={{ transform: `scaleX(${Math.max(job.progress, 0.02)})` }} />
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
          <p className="text-ink-2">Clipping downloads the video, transcribes it, asks the AI to pick the
            moments that stand alone, then renders face-framed {b.orientation} clips with karaoke captions.</p>
        </section>
      )}

      {!!clips?.length && (
        <ol ref={listRef} className="glass px-8 py-2">
          {clips.map((c) => (
            <ClipRow key={c.id} clip={c} pubs={pubs?.filter((p) => p.clip_idx === c.idx && !p.piece_id) ?? []} onPubsChanged={reloadPubs} onPreview={() => setPreview(c.id)} onPublish={() => setPublishing(c)}
              onReview={(status) => review(c.id, status)} onDelete={() => removeClip(c)} busy={running} />
          ))}
        </ol>
      )}
      {clips?.filter((c) => c.id === preview).map((c) => (
        <ClipPreview key={c.id} clip={c} onClose={() => setPreview(undefined)} onPublish={() => setPublishing(c)}
          onSaved={() => setRev((r) => r + 1)} />
      ))}
      {clips?.filter((c) => c.id === publishing?.id).map((c) => (
        <PublishDialog key={c.id} clip={c} onClose={() => setPublishing(undefined)} onSettings={onSettings}
          onChanged={() => { setPublishing(undefined); setRev((r) => r + 1) }} />
      ))}
      {planning && <CalendarDialog project={project} onClose={() => setPlanning(false)} onDone={() => setRev((r) => r + 1)}
        onSettings={onSettings} />}
    </>
  )
}

function ClipRow({ clip: c, pubs, onPubsChanged, onPreview, onPublish, onReview, onDelete, busy }: {
  clip: Clip; pubs: Publication[]; onPubsChanged: () => void; onPreview: () => void; onPublish: () => void
  onReview: (status: 'approved' | 'ready' | 'rejected') => void; onDelete: () => void; busy: boolean
}) {
  return (
    <li className="anim-slot grid grid-cols-[56px_72px_minmax(0,1fr)_auto] items-center gap-6 border-t border-line py-5 first:border-t-0 max-[900px]:grid-cols-[40px_56px_minmax(0,1fr)_auto]">
      <span className="tnum font-display text-xs text-accent-ink">{String(c.idx).padStart(2, '0')}</span>
      <button onClick={onPreview} className="overflow-hidden rounded-[8px] bg-black shadow-[inset_0_0_0_1px_rgb(17_18_20/0.1)]"
        aria-label={`Preview clip ${c.idx}`}>
        <img src={mediaUrl(c.cover_path)} alt="" className="aspect-video w-full object-cover" />
      </button>
      <div className="grid gap-1">
        <p className="flex items-baseline gap-2.5">
          <span data-selectable className="font-display text-[17px] font-semibold tracking-[-0.02em]">{c.title}</span>
          <span className="tnum shrink-0 rounded-full bg-accent px-2 py-0.5 text-2xs font-medium text-on-accent">{c.score}</span>
          <span className="tnum shrink-0 text-2xs text-ink-3">{(c.end_at - c.start_at).toFixed(0)}s</span>
        </p>
        <p data-selectable className="line-clamp-1 text-[13px] text-ink-2">{c.hook}</p>
        {c.status !== 'ready' && (
          <span className={cx('w-fit rounded-full px-2.5 py-0.5 text-2xs font-medium',
            c.status === 'rejected' ? 'bg-danger/15 text-danger' : 'bg-ok/15 text-ok')}>{label(c.status)}</span>
        )}
        <PublicationChips rows={pubs} onChanged={onPubsChanged} />
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
        <Button variant="ghost" className="!px-2" disabled={busy} onClick={onDelete} aria-label={`Delete clip ${c.idx}`}
          title="Delete this clip"><Trash size={13} /></Button>
      </div>
    </li>
  )
}

// Two columns: the clip fills the panel height on the left, everything readable or clickable sits in
// the right rail. Only the rail's middle band scrolls, so the publish button is never below the fold.
function ClipPreview({ clip: c, onClose, onPublish, onSaved }: {
  clip: Clip; onClose: () => void; onPublish: () => void; onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  return (
    <Dialog label={`Preview clip ${c.idx}`} width={1180} onClose={onClose}
      className="h-[min(780px,calc(100dvh-3rem))] grid-cols-[minmax(0,1fr)_368px] grid-rows-[minmax(0,1fr)] max-[1040px]:h-[calc(100dvh-3rem)] max-[1040px]:grid-cols-1 max-[1040px]:grid-rows-[minmax(0,1fr)_auto]">
      {/* the row is the dialog's height (not the video's), and a flex box gives max-h-full a definite height to
          resolve against, so a tall 9:16 clip scales down inside the panel instead of running past it */}
      <section className="flex min-h-0 items-center justify-center overflow-hidden p-3">
        <video src={mediaUrl(c.video_path)} controls className="max-h-full max-w-full rounded-field bg-black object-contain" />
      </section>

      <aside className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] border-l border-line max-[1040px]:border-l-0 max-[1040px]:border-t">
        <header className="grid gap-3 border-b border-line px-6 py-5">
          <div className="flex items-center justify-between gap-3">
            <span className={cx('rounded-full px-2.5 py-1 text-2xs font-medium', c.status === 'approved' ? 'chip-on'
              : c.status === 'rejected' ? 'bg-danger/15 text-danger' : 'bg-black/[0.06] text-ink-2')}>{label(c.status)}</span>
            <div className="-mr-3 flex shrink-0">
              {!editing && <Button variant="ghost" onClick={() => setEditing(true)} className="h-8"><PencilSimple size={13} />Edit copy</Button>}
              <Button variant="ghost" onClick={onClose} aria-label="Close preview" className="h-8"><X size={15} /></Button>
            </div>
          </div>
          <div className="grid gap-1">
            <h2 className="line-clamp-3 font-display text-[19px] font-semibold leading-snug tracking-[-0.02em] text-balance">{c.title}</h2>
            <p className="tnum text-xs text-ink-3">Clip {String(c.idx).padStart(2, '0')}, {(c.end_at - c.start_at).toFixed(0)} seconds, score {c.score}</p>
          </div>
        </header>

        {editing
          ? <CopyEditor clip={c} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); onSaved() }} />
          : <>
            <div className="grid content-start gap-6 overflow-y-auto px-6 py-5 text-[13px]">
              <section className="grid gap-1.5">
                <h3 className="text-xs text-ink-3">Hook</h3>
                <p data-selectable className="font-display text-[16px] font-semibold leading-snug tracking-[-0.01em] text-ink">{c.hook}</p>
              </section>
              <section className="grid gap-1.5">
                <h3 className="text-xs text-ink-3">Description</h3>
                <p data-selectable className="leading-relaxed text-pretty text-ink-2">{c.description}</p>
              </section>
              <section className="grid gap-1.5">
                <h3 className="text-xs text-ink-3">Why this moment</h3>
                <p data-selectable className="leading-relaxed text-pretty text-ink-2">{c.reason}</p>
              </section>
              <PostCopy clip={c} />
            </div>
            {c.status === 'approved' ? (
              <div className="flex justify-end border-t border-line px-6 py-4">
                <Button variant="primary" onClick={onPublish}><PaperPlaneTilt size={14} />Publish</Button>
              </div>
            ) : <div />}
          </>}
      </aside>
    </Dialog>
  )
}

/** The clip's own words, editable. Each platform's limit is checked by the backend, which says the numbers. */
function CopyEditor({ clip: c, onCancel, onSaved }: { clip: Clip; onCancel: () => void; onSaved: () => void }) {
  const [copy, setCopy] = useState({ title: c.title, hook: c.hook, description: c.description,
    hashtags: c.hashtags.join(' '), posts: { ...c.posts } })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BackendError>()

  async function save() {
    setBusy(true)
    setError(undefined)
    try {
      await call('clips.update', { id: c.id, title: copy.title.trim(), hook: copy.hook.trim(),
        description: copy.description.trim(), hashtags: copy.hashtags.split(/\s+/).filter(Boolean), posts: copy.posts })
      onSaved()
    } catch (e) {
      setError(e as BackendError)
      setBusy(false)
    }
  }

  const text = (key: 'title' | 'hook' | 'description', rows = 2) => (
    <Field label={label(key)}>
      {(id) => <Textarea id={id} rows={rows} value={copy[key]} onChange={(e) => setCopy({ ...copy, [key]: e.target.value })} />}
    </Field>
  )
  return (
    <>
      <div className="grid content-start gap-4 overflow-y-auto px-6 py-5">
        {text('title')}
        {text('hook')}
        {text('description', 3)}
        <Field label="Hashtags" hint="Separated by spaces.">
          {(id) => <Input id={id} value={copy.hashtags} onChange={(e) => setCopy({ ...copy, hashtags: e.target.value })} />}
        </Field>
        {POST_ORDER.map((n) => (
          <Field key={n} label={`${label(n)} post`} hint={<span className="tnum">{(copy.posts[n] ?? '').length} characters</span>}>
            {(id) => <Textarea id={id} rows={3} value={copy.posts[n] ?? ''}
              onChange={(e) => setCopy({ ...copy, posts: { ...copy.posts, [n]: e.target.value } })} />}
          </Field>
        ))}
        {error && <ErrorNote error={error} />}
      </div>
      <div className="flex justify-end gap-2 border-t border-line px-6 py-4">
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" disabled={busy || !copy.title.trim()} onClick={save}>{busy ? 'Saving…' : 'Save copy'}</Button>
      </div>
    </>
  )
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label, i) => ({ value: i + 1, label }))  // ISO weekdays
const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone
const day = (offset: number) => new Date(Date.now() + offset * 864e5).toLocaleDateString('sv')  // sv = YYYY-MM-DD
const when = (iso: string) => new Date(iso).toLocaleString(undefined,
  { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

/** ClipperAi's content calendar: every approved, unscheduled clip gets the next free posting slot. A plan is shown
 * first; nothing reaches Zernio until "Schedule". */
function CalendarDialog({ project, onClose, onDone, onSettings }: {
  project: P; onClose: () => void; onDone: () => void; onSettings?: () => void
}) {
  const zernio = useZernio().connected
  const [picked, setPicked] = useState<string[]>([])
  const [days, setDays] = useState<number[]>([1, 3, 5])
  const [times, setTimes] = useState('09:00, 18:00')
  const [start, setStart] = useState(day(1))
  const [plan, setPlan] = useState<CalendarPlan>()
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BackendError>()

  const parsed = times.split(/[,\s]+/).filter(Boolean)
  const badTime = parsed.find((t) => !/^([01]?\d|2[0-3]):[0-5]\d$/.test(t))
  const ok = !!zernio && picked.length > 0 && days.length > 0 && parsed.length > 0 && !badTime && !!start

  async function run(dry: boolean) {
    setBusy(true)
    setError(undefined)
    try {
      const result = await call<CalendarPlan>('publish.calendar', { project_id: project.id, account_ids: picked,
        days, times: parsed.map((t) => t.padStart(5, '0')), start, tz: ZONE, dry_run: dry })
      setPlan(result)
      if (!dry) { setDone(true); onDone() }
    } catch (e) {
      setError(e as BackendError)
    }
    setBusy(false)
  }

  // a changed setting voids the plan shown, so "Schedule" always sends exactly what was previewed
  const change = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPlan(undefined) }
  return (
    <Dialog label="Plan a posting calendar" width={620} onClose={onClose} className="grid-rows-[auto_minmax(0,1fr)_auto]">
      <header className="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
        <div>
          <p className="text-xs text-ink-3">Posting calendar</p>
          <h2 className="mt-0.5 font-display text-[18px] font-semibold tracking-[-0.02em]">{project.name}</h2>
        </div>
        <Button variant="ghost" onClick={onClose} aria-label="Close" className="-mt-2 -mr-3 h-8"><X size={15} /></Button>
      </header>

      <div className="grid content-start gap-5 overflow-y-auto px-6 py-5">
        {done ? (
          <p className="text-[13px] text-ink-2">Scheduled {plan?.scheduled.length} {plan?.scheduled.length === 1 ? 'clip' : 'clips'}.
            Each clip shows where and when it goes out.</p>
        ) : zernio === false ? <SetUpPosting onSettings={onSettings} onClose={onClose} /> : <>
          <ZernioPicker picked={picked} onChange={change(setPicked)} onSettings={() => { onClose(); onSettings?.() }} />
          <Choices legend="Posting days" multiple options={WEEKDAYS} value={days} onChange={change(setDays)} />
          <div className="grid grid-cols-2 gap-4">
            <Field label="Times" hint={`24-hour, separated by commas. Your time zone: ${ZONE}.`}
              error={badTime ? `"${badTime}" isn't a time like 09:00.` : undefined}>
              {(id) => <Input id={id} className="tnum" value={times} onChange={(e) => change(setTimes)(e.target.value)} />}
            </Field>
            <Field label="Starting">
              {(id) => <Input id={id} type="date" min={day(0)} value={start} onChange={(e) => change(setStart)(e.target.value)} />}
            </Field>
          </div>
        </>}

        {plan && (
          <ol className="grid gap-1.5 border-t border-line pt-4 text-[13px]">
            {plan.scheduled.map((s) => (
              <li key={s.clip_idx} className="grid grid-cols-[32px_minmax(0,1fr)_auto] items-baseline gap-3">
                <span className="tnum text-xs text-accent-ink">{String(s.clip_idx).padStart(2, '0')}</span>
                <span className="truncate text-ink">{s.title}</span>
                <span className="tnum text-ink-2">{when(s.due_at)}</span>
              </li>
            ))}
            {plan.left.length > 0 && (
              <li className="pt-2 text-xs text-ink-3">{plan.left.length} more {plan.left.length === 1 ? "clip doesn't" : "clips don't"} fit
                in the next 30 days. Add days or times to place them.</li>
            )}
          </ol>
        )}
        {error && <ErrorNote error={error} />}
      </div>

      <div className="flex justify-end gap-2 border-t border-line px-6 py-4">
        {done ? <Button variant="primary" onClick={onClose}>Done</Button> : <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          {plan
            ? <Button variant="primary" disabled={busy} onClick={() => run(false)}>
              <CalendarBlank size={14} />{busy ? 'Scheduling…' : `Schedule ${plan.scheduled.length}`}</Button>
            : <Button variant="primary" disabled={!ok || busy} onClick={() => run(true)}>{busy ? 'Planning…' : 'Show the plan'}</Button>}
        </>}
      </div>
    </Dialog>
  )
}

function PublishDialog({ clip: c, onClose, onChanged, onSettings }: {
  clip: Clip; onClose: () => void; onChanged: () => void; onSettings?: () => void
}) {
  return (
    <PostDialog title={c.title} kind="clip" onClose={onClose} onDone={onChanged} onSettings={onSettings}
      send={(account_ids, due_at) => call<Publication[]>('publish.zernio_publish', { project_id: c.project_id, clip_idx: c.idx, account_ids, due_at })} />
  )
}
