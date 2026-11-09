// Posting through Zernio: the guided setup (Settings), the account picker (publish dialog and calendar) and the
// status chips that show, on every clip, where it is scheduled or posted. Zernio itself lives in
// apps/backend/app/publish/zernio.py; this file only asks it things.
import { useEffect, useRef, useState } from 'react'
import { ArrowSquareOut, CalendarBlank, Check, CheckCircle, PaperPlaneTilt, Plus, WarningCircle, X } from '@phosphor-icons/react'
import { call, mediaUrl, studio, useQuery, BackendError, type Publication, type ScheduleItem, type ScheduleResult } from '../lib/studio'
import { Button, Dialog, ErrorNote, Field, Input, Select, cx } from './ui'

export type ZernioAccount = { id: string; platform: string; label: string; name: string; username: string; needs_reconnect: boolean }
type ZernioConnection = { connected: boolean; signup_url: string; keys_url: string }

const NETWORKS = [['tiktok', 'TikTok'], ['instagram', 'Instagram'], ['youtube', 'YouTube'], ['facebook', 'Facebook'],
  ['linkedin', 'LinkedIn'], ['twitter', 'X']] as const
export const TIKTOK_MUSIC = 'https://www.tiktok.com/legal/page/global/music-usage-confirmation/en'

export function useZernio() {
  const { data, reload } = useQuery<ZernioConnection>('publish.zernio_connection')
  return { connected: data?.connected, info: data, reload }
}

/** A numbered setup step: the number turns into a tick once the step is done. */
function Step({ n, done, title, children }: { n: number; done?: boolean; title: string; children?: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
      <span className={cx('grid size-7 place-items-center rounded-full text-xs font-semibold',
        done ? 'bg-accent text-on-accent' : 'bg-black/[0.06] text-ink-2')}>
        {done ? <Check size={13} weight="bold" /> : n}
      </span>
      <div className="grid gap-2.5 pt-1">
        <p className="text-[13px] font-medium text-ink">{title}</p>
        {children}
      </div>
    </li>
  )
}

/** Settings, Posting (and the first-run screens): three steps to set Zernio up, then the connected social accounts
 *  and a button per network to add one. Adding opens Zernio's sign-in for that network in the browser and waits for
 *  the account to land. `intro` off when the page already explains Zernio; `onChange` after connect or disconnect. */
export function ZernioSetup({ intro = true, onChange }: { intro?: boolean; onChange?: () => void }) {
  const zernio = useZernio()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BackendError>()

  async function save() {
    setBusy(true)
    setError(undefined)
    try { await call('publish.zernio_save_key', { api_key: key }); setKey(''); zernio.reload(); onChange?.() } catch (e) { setError(e as BackendError) }
    setBusy(false)
  }

  async function disconnect() {
    if (!confirm('Disconnect Zernio from this app? Posts already scheduled in Zernio still go out.')) return
    await call('publish.zernio_disconnect').catch((e) => setError(e as BackendError))
    zernio.reload()
    onChange?.()
  }

  if (zernio.connected === undefined) return <div className="h-40 animate-pulse rounded-field bg-black/[0.04]" />
  if (!zernio.connected) return (
    <div className="grid gap-5">
      {intro && <p className="text-[13px] text-ink-2">Zernio posts your clips to TikTok, Instagram, YouTube, Facebook, LinkedIn and X at the
        time you pick, even when this computer is off. It has a free plan. Set it up once:</p>}
      <ol className="grid gap-5">
        <Step n={1} title="Make a free Zernio account">
          <Button className="w-fit" onClick={() => studio.openExternal(zernio.info!.signup_url)}>
            Open zernio.com<ArrowSquareOut size={13} /></Button>
        </Step>
        <Step n={2} title="Create an API key in Zernio and copy it">
          <Button className="w-fit" onClick={() => studio.openExternal(zernio.info!.keys_url)}>
            Open Zernio API keys<ArrowSquareOut size={13} /></Button>
        </Step>
        <Step n={3} title="Paste the key here">
          <div className="flex gap-2">
            <Input type="password" autoComplete="off" spellCheck={false} value={key} placeholder="sk_…"
              aria-label="Zernio API key" onChange={(e) => setKey(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && key.trim() && save()} />
            <Button variant="primary" disabled={!key.trim() || busy} onClick={save}>{busy ? 'Checking…' : 'Connect'}</Button>
          </div>
          <p className="text-2xs text-ink-3">Saved encrypted on this computer. Only this app's posting uses it.</p>
        </Step>
      </ol>
      {error && <ErrorNote error={error} />}
    </div>
  )
  return <ZernioAccounts onDisconnect={disconnect} />
}

function ZernioAccounts({ onDisconnect }: { onDisconnect: () => void }) {
  const { data: accounts, error: loadError, reload } = useQuery<ZernioAccount[]>('publish.zernio_accounts')
  const [waiting, setWaiting] = useState<string>()
  const [error, setError] = useState<BackendError>()
  const poll = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearInterval(poll.current), [])

  async function add(platform: string, label: string) {
    setError(undefined)
    try {
      studio.openExternal(await call<string>('publish.zernio_connect_url', { platform }))
      const before = JSON.stringify(accounts)
      setWaiting(label)
      window.clearInterval(poll.current)
      const started = Date.now()
      poll.current = window.setInterval(async () => {
        const now = await call<ZernioAccount[]>('publish.zernio_accounts').catch(() => null)
        if ((now && JSON.stringify(now) !== before) || Date.now() - started > 300_000) {
          window.clearInterval(poll.current); setWaiting(undefined); reload()
        }
      }, 3000)
    } catch (e) { setError(e as BackendError) }
  }

  return (
    <div className="grid gap-5">
      <div className="flex items-center justify-between gap-4">
        <p className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ok"><CheckCircle size={16} weight="fill" />Zernio is connected</p>
        <Button variant="ghost" onClick={onDisconnect}>Disconnect</Button>
      </div>

      <section className="grid gap-2">
        <h3 className="text-[13px] font-medium text-ink">Your accounts</h3>
        {loadError && <ErrorNote error={loadError} action={<Button onClick={reload}>Try again</Button>} />}
        {accounts?.length === 0 && <p className="text-[13px] text-ink-2">No accounts yet. Add the first one below.</p>}
        <ul className="grid gap-1.5">
          {accounts?.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 rounded-[10px] bg-ground px-3.5 py-2.5 text-[13px]">
              <span className="min-w-0 truncate"><span className="font-medium text-ink">{a.label}</span>
                <span className="text-ink-2"> · {a.name}{a.username && a.username !== a.name ? ` (@${a.username})` : ''}</span></span>
              {a.needs_reconnect
                ? <Button variant="ghost" className="h-8 shrink-0 text-danger" onClick={() => add(a.platform, a.label)}>
                    <WarningCircle size={14} />Sign in again</Button>
                : <span className="shrink-0 text-2xs text-ok">Ready</span>}
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-2">
        <h3 className="text-[13px] font-medium text-ink">Add an account</h3>
        <div className="flex flex-wrap gap-1.5">
          {NETWORKS.map(([id, label]) => (
            <Button key={id} variant="ghost" disabled={!!waiting} className="shadow-[inset_0_0_0_1px_var(--color-line)]"
              onClick={() => add(id, label)}><Plus size={13} />{label}</Button>
          ))}
        </div>
        <p className="text-2xs text-ink-3">{waiting
          ? `Sign in to ${waiting} in the browser window that opened. The account shows up here when you're done.`
          : 'Each one opens a sign-in page in your browser. You approve there, nothing to copy.'}</p>
      </section>
      {error && <ErrorNote error={error} />}
    </div>
  )
}

/** Zernio accounts as toggles, for the post dialog and the calendar. `unsupported` names why an account can't
 *  take this post (a still image on YouTube), which disables it with that reason. */
export function ZernioPicker({ picked, onChange, onSettings, unsupported }: {
  picked: string[]; onChange: (ids: string[]) => void; onSettings?: () => void; unsupported?: (a: ZernioAccount) => string | undefined
}) {
  const { data: accounts, error } = useQuery<ZernioAccount[]>('publish.zernio_accounts')
  if (error) return <ErrorNote error={error} />
  if (!accounts) return <div className="h-24 animate-pulse rounded-field bg-black/[0.04]" />
  if (accounts.length === 0) return (
    <div className="grid gap-3 rounded-field bg-ground p-4 text-[13px]">
      <p className="text-ink-2">No social accounts are connected in Zernio yet. Add one in Settings, Posting.</p>
      {onSettings && <Button className="w-fit" onClick={onSettings}>Open Settings</Button>}
    </div>
  )
  const tiktok = accounts.some((a) => a.platform === 'tiktok' && picked.includes(a.id))
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1.5 text-[13px] font-medium text-ink">Post to</legend>
      {accounts.map((a) => { const why = unsupported?.(a); return (
        <button key={a.id} type="button" disabled={a.needs_reconnect || !!why}
          onClick={() => onChange(picked.includes(a.id) ? picked.filter((x) => x !== a.id) : [...picked, a.id])}
          className={cx('flex items-center justify-between gap-3 rounded-[10px] px-3.5 py-2.5 text-left text-[13px] transition-colors duration-150 disabled:opacity-50',
            picked.includes(a.id) ? 'chip-on' : 'text-ink-2 hover:bg-black/[0.05]')}>
          <span className="truncate"><span className="font-medium">{a.label}</span> · {a.name}</span>
          <span className="shrink-0 text-2xs text-ink-3">{a.needs_reconnect ? 'Sign in again in Settings' : why ?? (picked.includes(a.id) ? 'Selected' : '')}</span>
        </button>
      ) })}
      {tiktok && (
        <p className="mt-1 text-2xs text-ink-3">Posting to TikTok means you agree to TikTok's{' '}
          <button type="button" className="underline underline-offset-2 hover:text-ink" onClick={() => studio.openExternal(TIKTOK_MUSIC)}>
            Music Usage Confirmation</button>.</p>
      )}
    </fieldset>
  )
}

const STATUS: Record<string, { text: string; tone: string }> = {
  scheduled: { text: 'Scheduled', tone: 'bg-black/[0.06] text-ink-2' },
  sending: { text: 'Posting now', tone: 'bg-accent/40 text-ink' },
  sent: { text: 'Posted', tone: 'bg-ok/15 text-ok' },
  error: { text: 'Failed', tone: 'bg-danger/15 text-danger' },
  canceled: { text: 'Cancelled', tone: 'bg-black/[0.06] text-ink-3' },
}
const at = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

/** Where one clip is going: a chip per network with its state and time. Posted ones open the live post; a
 *  scheduled or failed one can be taken back with its x. */
export function PublicationChips({ rows, onChanged }: { rows: Publication[]; onChanged: () => void }) {
  const [error, setError] = useState<BackendError>()
  if (!rows.length) return null
  async function remove(p: Publication) {
    const scheduled = p.status !== 'error'
    if (scheduled && !confirm(`Unschedule this clip on ${p.channel_name}?`)) return
    setError(undefined)
    try { await call('publish.remove', { publication_id: p.id }); onChanged() } catch (e) { setError(e as BackendError) }
  }
  return (
    <div className="grid gap-1.5">
      <ul className="flex flex-wrap gap-1.5" aria-label="Where this clip is posted">
        {rows.map((p) => {
          const s = STATUS[p.status] ?? STATUS.scheduled
          const when = p.status === 'sent' ? p.sent_at : p.due_at
          return (
            <li key={p.id} title={p.error ?? undefined}
              className={cx('inline-flex items-center gap-1.5 rounded-full py-0.5 pl-2.5 text-2xs font-medium', s.tone,
                p.status === 'sent' ? 'pr-2.5' : 'pr-1')}>
              {p.external_link
                ? <button type="button" className="underline-offset-2 hover:underline" onClick={() => studio.openExternal(p.external_link!)}>
                    {s.text} · {p.channel_name}</button>
                : <span>{s.text} · {p.channel_name}{when && p.status !== 'error' ? ` · ${at(when)}` : ''}</span>}
              {p.status !== 'sent' && (
                <button type="button" aria-label={p.status === 'error' ? 'Clear' : 'Unschedule'} onClick={() => remove(p)}
                  className="grid size-4 place-items-center rounded-full hover:bg-black/10"><X size={9} weight="bold" /></button>
              )}
            </li>
          )
        })}
      </ul>
      {rows.some((p) => p.status === 'error') && (
        <p className="text-2xs text-danger">{rows.find((p) => p.status === 'error')!.error}</p>
      )}
      {error && <ErrorNote error={error} />}
    </div>
  )
}

/** Shown wherever posting is offered before Zernio is set up. */
export function SetUpPosting({ onSettings, onClose }: { onSettings?: () => void; onClose: () => void }) {
  return (
    <div className="grid gap-3 rounded-field bg-ground p-4 text-[13px]">
      <p className="font-medium text-ink">Set up posting once</p>
      <p className="text-ink-2">Connect Zernio in Settings, under Posting. It takes about two minutes, and after that
        anything you make can be posted from here.</p>
      {onSettings && <Button variant="primary" className="w-fit" onClick={() => { onClose(); onSettings() }}>Open Settings</Button>}
    </div>
  )
}

/** Post or schedule one thing (a clip, a quote image, a narrated video) through Zernio: pick accounts, pick a time
 *  or leave it empty, press the button. `send` does the posting; `video` false disables video-only networks. */
export function PostDialog({ title, kind, video = true, send, onClose, onDone, onSettings }: {
  title: string; kind: string; video?: boolean; send: (accountIds: string[], dueAt?: string) => Promise<Publication[]>
  onClose: () => void; onDone: () => void; onSettings?: () => void
}) {
  const zernio = useZernio().connected
  const [picked, setPicked] = useState<string[]>([])
  const [when, setWhen] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BackendError>()
  const [sent, setSent] = useState<Publication[]>()

  async function post() {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      setSent(await send(picked, when ? new Date(when).toISOString() : undefined))
      onDone()
    } catch (e) {
      setError(e as BackendError)
    }
    setBusy(false)
  }

  return (
    <Dialog label={`Post ${kind}`} width={560} onClose={onClose} className="grid-rows-[auto_minmax(0,1fr)_auto]">
      <header className="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
        <div className="min-w-0">
          <p className="text-xs text-ink-3">Post or schedule this {kind}</p>
          <h2 className="mt-0.5 line-clamp-2 font-display text-[18px] font-semibold tracking-[-0.02em] text-balance">{title}</h2>
        </div>
        <Button variant="ghost" onClick={onClose} aria-label="Close" className="-mt-2 -mr-3 h-8"><X size={15} /></Button>
      </header>

      <div className="grid content-start gap-5 overflow-y-auto px-6 py-5">
        {zernio === undefined && <div className="h-24 animate-pulse rounded-field bg-black/[0.04]" />}
        {zernio === false && <SetUpPosting onSettings={onSettings} onClose={onClose} />}
        {sent && <SentList rows={sent} />}
        {zernio && !sent && <>
          <ZernioPicker picked={picked} onChange={setPicked} onSettings={() => { onClose(); onSettings?.() }}
            unsupported={video ? undefined : (a) => (a.platform === 'youtube' ? 'Videos only' : undefined)} />
          <Field label="When" hint="Leave empty to post in about two minutes. Zernio posts at this time even if this computer is off.">
            {(id) => <Input id={id} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />}
          </Field>
        </>}
        {error && <ErrorNote error={error} />}
      </div>

      <div className="flex justify-end gap-2 border-t border-line px-6 py-4">
        {sent ? <Button variant="primary" onClick={onClose}>Done</Button> : <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          {zernio && (
            <Button variant="primary" disabled={!picked.length || busy} onClick={post}>
              <PaperPlaneTilt size={14} />{busy ? 'Uploading to Zernio…' : when ? 'Schedule' : 'Post now'}
            </Button>
          )}
        </>}
      </div>
    </Dialog>
  )
}

/** The answer after pressing Post: per account, scheduled for when, or why Zernio refused it. */
function SentList({ rows }: { rows: Publication[] }) {
  const ok = rows.filter((r) => r.status !== 'error')
  return (
    <div className="grid gap-3">
      {ok.length > 0 && (
        <p className="inline-flex items-center gap-1.5 text-[14px] font-medium text-ok"><CheckCircle size={18} weight="fill" />
          {ok.length === rows.length ? 'Sent to Zernio' : `Sent to Zernio for ${ok.length} of ${rows.length} accounts`}</p>
      )}
      <ul className="grid gap-1.5 text-[13px]">
        {rows.map((r) => (
          <li key={r.id} className={cx('grid gap-0.5 rounded-[10px] px-3.5 py-2.5', r.status === 'error' ? 'bg-danger/10' : 'bg-ground')}>
            <span className="font-medium text-ink">{r.channel_name}</span>
            <span className={r.status === 'error' ? 'text-danger' : 'text-ink-2'}>{r.status === 'error'
              ? r.error : `Goes out ${r.due_at ? at(r.due_at) : 'shortly'}.`}</span>
          </li>
        ))}
      </ul>
      {ok.length > 0 && <p className="text-2xs text-ink-3">Zernio posts it at that time, even if this computer is off. The label on this
        item changes from Scheduled to Posted once it is live.</p>}
    </div>
  )
}

const local = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16)  // datetime-local value
/** How far apart "Schedule all" spaces the posts (owner 2026-11-08), in minutes. */
const EVERY = [{ value: 10, label: 'Every 10 minutes' }, { value: 15, label: 'Every 15 minutes' }, { value: 60, label: 'Every hour' },
  { value: 1440, label: 'Every day' }, { value: 2880, label: 'Every other day' }]
/** The first slot: 15 minutes from now, on the next 5-minute mark (time for the uploads to finish). */
const soon = () => { const d = new Date(Date.now() + 15 * 6e4); d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0); return local(d) }
/** Each included post's time: the first one at `first`, the rest `every` minutes apart, in list order. */
const spaced = (keys: string[], first: string, every: number) =>
  Object.fromEntries(keys.map((k, i) => [k, first ? local(new Date(new Date(first).getTime() + i * every * 6e4)) : '']))

/** "Schedule all" (owner 2026-11-08): every post not yet scheduled, each with its own date and time, sent to the
 *  chosen accounts in one go. Times start one a day at 18:00 and are edited per post; untick any to leave it out. */
export function ScheduleAllDialog({ projectId, items, onClose, onDone, onSettings }: {
  projectId: string; items: ScheduleItem[]; onClose: () => void; onDone: () => void; onSettings?: () => void
}) {
  const zernio = useZernio().connected
  const [picked, setPicked] = useState<string[]>([])
  const [first, setFirst] = useState(soon)
  const [every, setEvery] = useState(15)
  const [skip, setSkip] = useState<string[]>([])
  const [times, setTimes] = useState<Record<string, string>>(() => spaced(items.map((it) => it.key), first, every))
  // the first time, the spacing or the set of posts changed: lay every included post out again (edits per post stay
  // until then); a skipped post keeps no slot, so the rest close up
  const relay = (f: string, e: number, sk: string[]) =>
    setTimes(spaced(items.filter((it) => !sk.includes(it.key)).map((it) => it.key), f, e))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BackendError>()
  const [results, setResults] = useState<Record<string, ScheduleResult>>()
  const chosen = items.filter((it) => !skip.includes(it.key))
  const missing = chosen.find((it) => !times[it.key])
  const images = chosen.some((it) => !it.video)

  async function send() {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      const out = await call<ScheduleResult[]>('publish.schedule', { project_id: projectId, account_ids: picked,
        items: chosen.map((it) => ({ clip_idx: it.clip_idx, piece_id: it.piece_id, due_at: new Date(times[it.key]).toISOString() })) })
      setResults(Object.fromEntries(out.map((r) => [r.key, r])))
      onDone()
    } catch (e) {
      setError(e as BackendError)
    }
    setBusy(false)
  }

  const sent = results ? Object.values(results) : []
  const okCount = sent.filter((r) => r.ok).length
  return (
    <Dialog label="Schedule all" width={680} onClose={onClose} className="grid-rows-[auto_minmax(0,1fr)_auto]">
      <header className="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
        <div>
          <p className="text-xs text-ink-3">Schedule all</p>
          <h2 className="mt-0.5 font-display text-[18px] font-semibold tracking-[-0.02em]">
            {items.length} {items.length === 1 ? 'post' : 'posts'}, each at its own time</h2>
        </div>
        <Button variant="ghost" onClick={onClose} aria-label="Close" className="-mt-2 -mr-3 h-8"><X size={15} /></Button>
      </header>

      <div className="grid content-start gap-5 overflow-y-auto px-6 py-5">
        {zernio === undefined && <div className="h-24 animate-pulse rounded-field bg-black/[0.04]" />}
        {zernio === false && <SetUpPosting onSettings={onSettings} onClose={onClose} />}
        {results && (
          <p className="inline-flex items-center gap-1.5 text-[14px] font-medium text-ok"><CheckCircle size={18} weight="fill" />
            {okCount === sent.length ? `All ${okCount} sent to Zernio` : `${okCount} of ${sent.length} sent to Zernio`}</p>
        )}
        {zernio && !results && (
          <ZernioPicker picked={picked} onChange={setPicked} onSettings={() => { onClose(); onSettings?.() }}
            unsupported={images && chosen.every((it) => !it.video) ? (a) => (a.platform === 'youtube' ? 'Videos only' : undefined) : undefined} />
        )}
        {zernio && (
          <fieldset className="grid gap-1">
            <legend className="mb-1.5 text-[13px] font-medium text-ink">When each one goes out</legend>
            {!results && (
              <div className="mb-3 grid grid-cols-2 gap-4">
                <Field label="First post">
                  {(id) => <Input id={id} type="datetime-local" className="tnum" value={first} min={local(new Date())}
                    onChange={(e) => { setFirst(e.target.value); relay(e.target.value, every, skip) }} />}
                </Field>
                <Field label="Then">
                  {(id) => <Select id={id} value={String(every)} options={EVERY.map((o) => ({ value: String(o.value), label: o.label }))}
                    onChange={(v) => { setEvery(Number(v)); relay(first, Number(v), skip) }} />}
                </Field>
              </div>
            )}
            <p className="mb-2 text-xs text-ink-3">Change any single time below if you like. Your time zone:
              {' '}{Intl.DateTimeFormat().resolvedOptions().timeZone}. Zernio posts at these times even if this computer is off.{images && chosen.some((it) => it.video) ? ' YouTube takes the videos only.' : ''}</p>
            <ol className="grid gap-1.5">
              {items.map((it) => {
                const off = skip.includes(it.key), r = results?.[it.key]
                return (
                  <li key={it.key} className={cx('grid grid-cols-[auto_44px_minmax(0,1fr)_200px] items-center gap-3 rounded-[10px] px-2 py-1.5',
                    r && !r.ok && 'bg-danger/10', off && 'opacity-50')}>
                    <input type="checkbox" checked={!off} disabled={!!results} aria-label={`Include ${it.title}`}
                      onChange={() => { const sk = off ? skip.filter((k) => k !== it.key) : [...skip, it.key]; setSkip(sk); relay(first, every, sk) }}
                      className="size-4 accent-[var(--color-ink)]" />
                    {it.cover ? <img src={mediaUrl(it.cover)} alt="" className="aspect-square w-11 rounded-[8px] object-cover" />
                      : <span className="aspect-square w-11 rounded-[8px] bg-black/[0.06]" />}
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] text-ink">{it.title}</span>
                      {r ? <span className={cx('block text-2xs', r.ok ? 'text-ok' : 'text-danger')}>{r.ok ? 'Scheduled' : r.error}</span>
                        : <span className="block text-2xs text-ink-3">{it.video ? 'Video' : 'Image'}</span>}
                    </span>
                    <Input type="datetime-local" aria-label={`When ${it.title} goes out`} value={times[it.key] ?? ''} min={local(new Date())}
                      disabled={off || !!results} onChange={(e) => setTimes({ ...times, [it.key]: e.target.value })} className="tnum !h-9 !text-xs" />
                  </li>
                )
              })}
            </ol>
          </fieldset>
        )}
        {error && <ErrorNote error={error} />}
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-line px-6 py-4">
        {results ? <Button variant="primary" onClick={onClose}>Done</Button> : <>
          {missing && <span className="mr-auto text-xs text-danger">Pick a time for every post, or untick it.</span>}
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          {zernio && (
            <Button variant="primary" disabled={!picked.length || !chosen.length || !!missing || busy} onClick={send}>
              <CalendarBlank size={14} />{busy ? 'Uploading to Zernio…' : `Schedule ${chosen.length}`}
            </Button>
          )}
        </>}
      </div>
    </Dialog>
  )
}
