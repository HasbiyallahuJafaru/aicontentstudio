// Footage review (owner decision 2026-11-07): nothing full-size downloads until the user has seen the options.
// Each piece shows its candidates as thumbnails with the AI's picks pre-selected and numbered in play order; a click
// swaps a shot (saved at once, so a restart keeps it), and one button under the shots downloads exactly the picked
// footage and then renders every piece (the "visuals_render" job). Pasted Pexels or Unsplash links (several at once,
// separated by commas, spaces or new lines) add those exact photos and clips, played first in the order pasted; the
// piece grows to hold them all (owner 2026-11-12).
import { useRef, useState, type CSSProperties } from 'react'
import { Books, DownloadSimple, LinkSimple, Play } from '@phosphor-icons/react'
import { call, mediaUrl, useQuery, BackendError, type Asset, type FootageOption, type Piece } from '../lib/studio'
import { Button, Dialog, ErrorNote, Textarea, cx } from './ui'

type Added = { added: FootageOption[]; picked: string[]; want: number; skipped: { url?: string; id?: string; reason: string }[] }

export function FootageReview({ pieces, onStarted, disabled }: {
  pieces: Piece[]; onStarted: () => void; disabled?: boolean
}) {
  const [picks, setPicks] = useState<Record<string, string[]>>(
    () => Object.fromEntries(pieces.map((p) => [p.id, p.content.review!.picked])))
  const [error, setError] = useState<BackendError>()
  const [starting, setStarting] = useState(false)
  const [added, setAdded] = useState<Record<string, FootageOption[]>>({})  // linked shots, shown before the backend reload
  const [links, setLinks] = useState<Record<string, string>>({})
  const [adding, setAdding] = useState<string>()
  const [browsing, setBrowsing] = useState<Piece>()  // the piece whose library picker is open
  const [wants, setWants] = useState<Record<string, number>>({})  // a piece grows when links outnumber its shots
  const [skipped, setSkipped] = useState<Record<string, Added['skipped']>>({})
  // each piece's saves run in order (a later click never lands before an earlier one), and "Download and render"
  // waits for all of them, so the job downloads exactly what is on screen
  const saving = useRef<Record<string, Promise<void>>>({})
  const total = Object.values(picks).reduce((n, k) => n + k.length, 0)
  const missing = pieces.filter((p) => !picks[p.id]?.length)

  async function toggle(piece: Piece, key: string) {
    const want = wants[piece.id] ?? piece.content.review!.want
    const now = picks[piece.id] ?? []
    // a full set swaps its last shot for the new one, so a click always does something visible
    const next = now.includes(key) ? now.filter((k) => k !== key) : now.length < want ? [...now, key] : [...now.slice(0, -1), key]
    setPicks({ ...picks, [piece.id]: next })
    setError(undefined)
    if (!next.length) return  // nothing to save yet: the backend refuses an empty pick, the button waits for one
    const save = (saving.current[piece.id] ?? Promise.resolve()).then(() =>
      call('visuals.pick', { piece_id: piece.id, keys: next }).then(() => undefined))
    saving.current[piece.id] = save.catch(() => undefined)
    try { await save } catch (e) {
      setPicks((p) => ({ ...p, [piece.id]: now }))  // not saved: show what the backend really holds
      setError(e as BackendError)
    }
  }

  async function addLink(piece: Piece) {
    const urls = (links[piece.id] ?? '').trim()
    if (!urls) return
    setAdding(piece.id)
    setError(undefined)
    try {
      await (saving.current[piece.id] ?? Promise.resolve())  // a pick still saving lands first
      const r = await call<Added>('visuals.add_links', { piece_id: piece.id, urls })
      landed(piece, r)
      // keep only the links that didn't land, so they can be fixed and added again
      setLinks((l) => ({ ...l, [piece.id]: r.skipped.map((x) => x.url ?? '').filter(Boolean).join(', ') }))
    } catch (e) { setError(e as BackendError) } finally { setAdding(undefined) }
  }

  /** your own picks (links or library items) now lead the piece: show them, their order and the grown count */
  function landed(piece: Piece, r: Added) {
    setAdded((a) => ({ ...a, [piece.id]: [...r.added, ...(a[piece.id] ?? []).filter((o) => !r.added.some((x) => x.key === o.key))] }))
    setPicks((p) => ({ ...p, [piece.id]: r.picked }))
    setWants((w) => ({ ...w, [piece.id]: r.want }))
    setSkipped((k) => ({ ...k, [piece.id]: r.skipped }))
  }

  async function addFromLibrary(piece: Piece, ids: string[]) {
    setAdding(piece.id)
    setError(undefined)
    try {
      await (saving.current[piece.id] ?? Promise.resolve())
      landed(piece, await call<Added>('visuals.add_from_library', { piece_id: piece.id, asset_ids: ids }))
      setBrowsing(undefined)
    } catch (e) { setError(e as BackendError) } finally { setAdding(undefined) }
  }

  async function confirm() {
    setStarting(true)
    setError(undefined)
    try {
      await Promise.all(Object.values(saving.current))  // every pick saved first
      await call('jobs.start', { project_id: pieces[0].project_id, kind: 'visuals_render' })
      onStarted()
    } catch (e) { setError(e as BackendError) } finally { setStarting(false) }
  }

  return (
    <section aria-label="Choose the footage" className="glass anim-drift mb-8 grid grid-cols-1 gap-7 p-8">
      <div className="grid gap-1.5">
        <h2 className="font-display text-[22px] font-semibold tracking-[-0.02em]">Choose the footage</h2>
        <p className="max-w-[62ch] text-[13px] leading-relaxed text-ink-2">
          Nothing has been downloaded yet. The studio's picks are numbered in the order they play; click any shot to
          swap it. When you're happy, press Download and render below the shots.
        </p>
      </div>

      {pieces.map((p) => {
        const review = p.content.review!
        const mine = picks[p.id] ?? []
        const want = wants[p.id] ?? review.want
        const extra = added[p.id] ?? []
        const options = [...extra, ...review.options.filter((o) => !extra.some((x) => x.key === o.key))]
        return (
          <div key={p.id} className="grid gap-3 border-t border-line pt-6">
            <div className="flex items-baseline justify-between gap-4">
              <p className="min-w-0 max-w-[80ch] text-[14px] font-medium leading-snug text-ink">
                <span className="tnum mr-3 font-display text-xs text-accent-ink">{String(p.idx).padStart(3, '0')}</span>{p.content.quote.text}
              </p>
              <span className="tnum shrink-0 text-xs text-ink-3">{mine.length} of {want} {want === 1 ? 'shot' : 'shots'}</span>
            </div>
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-4 p-2">
              {options.map((o, i) => {
                const order = mine.indexOf(o.key)
                const on = order >= 0
                return (
                  <li key={o.key} className="anim-slot" style={{ '--i': Math.min(i, 12) } as CSSProperties}>
                    <button type="button" onClick={() => toggle(p, o.key)} aria-pressed={on}
                      title={`${o.candidate.creator || 'Unknown creator'} · ${o.queries.join(', ')}`}
                      className={cx('group relative block aspect-[9/16] w-full overflow-hidden rounded-[14px] bg-black/30 transition-[box-shadow,transform] duration-200',
                        on ? 'halo'
                          : 'shadow-[inset_0_0_0_1px_rgb(17_18_20/0.1)] hover:-translate-y-0.5')}>
                      <img src={mediaUrl(o.thumb)} alt={`Footage option by ${o.candidate.creator || 'unknown'}`} loading="lazy"
                        className={cx('absolute inset-0 size-full object-cover transition-opacity duration-200', !on && 'opacity-70 group-hover:opacity-100')} />
                      {on && (
                        <span className="tnum absolute left-2 top-2 grid size-6 place-items-center rounded-full bg-pop text-2xs font-semibold text-white">{order + 1}</span>
                      )}
                      <span className="absolute inset-x-1.5 bottom-1.5 flex flex-wrap items-center gap-1">
                        {o.candidate.asset_type === 'video' && (
                          <span className="inline-flex items-center gap-0.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                            <Play size={7} weight="fill" />{Math.round(o.candidate.duration)}s
                          </span>
                        )}
                        {o.note && (
                          <span className="rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] text-white/80">
                            {o.note === 'used' ? 'Used before' : 'Like recent footage'}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
            <form className="grid max-w-[640px] gap-2" onSubmit={(e) => { e.preventDefault(); void addLink(p) }}>
              <Textarea rows={2} aria-label={`Add your own ${review.type === 'video' ? 'clips and photos' : 'photos'} for piece ${p.idx}`}
                placeholder={review.type === 'video'
                  ? 'Paste Pexels video or photo links, or Unsplash photo links, separated by commas'
                  : 'Paste Pexels or Unsplash photo links, separated by commas'}
                value={links[p.id] ?? ''} onChange={(e) => setLinks({ ...links, [p.id]: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void addLink(p) } }}
                disabled={disabled || adding === p.id} />
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" disabled={disabled || adding === p.id || !(links[p.id] ?? '').trim()}>
                  <LinkSimple size={14} weight="bold" />{adding === p.id ? 'Adding…' : 'Add links'}
                </Button>
                <Button type="button" onClick={() => setBrowsing(p)} disabled={disabled || adding === p.id}>
                  <Books size={14} weight="bold" />From your library
                </Button>
                {review.type === 'video' && (
                  <span className="text-xs text-ink-3">Each clip lends a short slice, never its full length.</span>
                )}
              </div>
              {!!skipped[p.id]?.length && (
                <ul className="grid gap-1 text-xs text-danger">
                  {skipped[p.id].map((x) => <li key={x.url ?? x.id} className="break-all">{x.reason} <span className="text-ink-3">{x.url ?? ''}</span></li>)}
                </ul>
              )}
            </form>
          </div>
        )
      })}

      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
        <p className="max-w-[56ch] text-[13px] text-ink-2">
          {missing.length
            ? <span className="text-danger">Pick at least one shot for piece {missing.map((p) => String(p.idx).padStart(3, '0')).join(', ')}.</span>
            : `Downloads the ${total} picked ${total === 1 ? 'shot' : 'shots'}, then renders every piece. You can watch the progress at the top of this page.`}
        </p>
        <Button variant="primary" onClick={confirm} disabled={disabled || starting || !!missing.length || !total}>
          <DownloadSimple size={14} weight="bold" />{starting ? 'Starting…' : 'Download and render'}
        </Button>
      </div>
      {error && <ErrorNote error={error} />}
      {browsing && (
        <LibraryPicker photosOnly={browsing.content.review!.type === 'image'} busy={adding === browsing.id}
          onClose={() => setBrowsing(undefined)} onUse={(ids) => addFromLibrary(browsing, ids)} />
      )}
    </section>
  )
}

/** Photos and clips already downloaded (owner 2026-11-12: "reuse already downloaded Pexels and Unsplash content").
 *  Tick any number; they are added to the piece in the order ticked and play first. Nothing downloads again. */
function LibraryPicker({ photosOnly, busy, onClose, onUse }: {
  photosOnly: boolean; busy: boolean; onClose: () => void; onUse: (ids: string[]) => void
}) {
  const { data, error } = useQuery<Asset[]>('assets.list')
  const [chosen, setChosen] = useState<string[]>([])
  const items = (data ?? []).filter((a) => !photosOnly || a.asset_type === 'image')
  const toggle = (id: string) => setChosen((c) => c.includes(id) ? c.filter((x) => x !== id) : [...c, id])
  return (
    <Dialog label="Your library" width={760} onClose={onClose} locked={busy}>
      <div className="grid gap-5 p-7">
        <div className="grid gap-1">
          <h3 className="font-display text-[19px] font-semibold tracking-[-0.02em]">Reuse from your library</h3>
          <p className="text-[13px] text-ink-2">
            {photosOnly ? 'Photos' : 'Photos and clips'} you have downloaded before. Tick the ones you want; they play in the order you tick them.
          </p>
        </div>
        {error && <ErrorNote error={error} />}
        {data && !items.length && <p className="text-[13px] text-ink-2">Nothing downloaded yet. Your picks are saved here after the first render.</p>}
        <ul className="grid max-h-[52vh] grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-3 overflow-y-auto p-1">
          {items.map((a) => {
            const order = chosen.indexOf(a.id)
            return (
              <li key={a.id}>
                <button type="button" onClick={() => toggle(a.id)} aria-pressed={order >= 0}
                  title={`${a.creator || 'Unknown creator'} · ${a.provider}`}
                  className={cx('relative block aspect-[9/16] w-full overflow-hidden rounded-[12px] bg-black/30',
                    order >= 0 ? 'halo' : 'shadow-[inset_0_0_0_1px_rgb(17_18_20/0.1)]')}>
                  <img src={mediaUrl(a.thumb_path)} alt={`${a.asset_type === 'video' ? 'Clip' : 'Photo'} by ${a.creator || 'unknown'}`}
                    loading="lazy" className={cx('absolute inset-0 size-full object-cover', order < 0 && 'opacity-80')} />
                  {order >= 0 && (
                    <span className="tnum absolute left-1.5 top-1.5 grid size-6 place-items-center rounded-full bg-pop text-2xs font-semibold text-white">{order + 1}</span>
                  )}
                  {a.asset_type === 'video' && (
                    <span className="absolute bottom-1.5 left-1.5 inline-flex items-center gap-0.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                      <Play size={7} weight="fill" />{Math.round(a.duration)}s
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
        <div className="flex items-center justify-end gap-3">
          <Button type="button" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" type="button" onClick={() => onUse(chosen)} disabled={busy || !chosen.length}>
            {busy ? 'Adding…' : chosen.length ? `Use ${chosen.length} from library` : 'Use from library'}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
