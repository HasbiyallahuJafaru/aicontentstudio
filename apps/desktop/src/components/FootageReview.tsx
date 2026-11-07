// Footage review (owner decision 2026-11-07): nothing full-size downloads until the user has seen the options.
// Each piece shows its candidates as thumbnails with the AI's picks pre-selected and numbered in play order; a click
// swaps a shot (saved at once, so a restart keeps it), and one button downloads exactly the picked footage.
import { useState, type CSSProperties } from 'react'
import { DownloadSimple, Play } from '@phosphor-icons/react'
import { call, mediaUrl, BackendError, type Piece } from '../lib/studio'
import { Button, ErrorNote, cx } from './ui'

export function FootageReview({ pieces, onStarted, disabled }: {
  pieces: Piece[]; onStarted: () => void; disabled?: boolean
}) {
  const [picks, setPicks] = useState<Record<string, string[]>>(
    () => Object.fromEntries(pieces.map((p) => [p.id, p.content.review!.picked])))
  const [error, setError] = useState<BackendError>()
  const [starting, setStarting] = useState(false)
  const total = Object.values(picks).reduce((n, k) => n + k.length, 0)
  const missing = pieces.filter((p) => !picks[p.id]?.length)

  async function toggle(piece: Piece, key: string) {
    const want = piece.content.review!.want
    const now = picks[piece.id] ?? []
    // a full set swaps its last shot for the new one, so a click always does something visible
    const next = now.includes(key) ? now.filter((k) => k !== key) : now.length < want ? [...now, key] : [...now.slice(0, -1), key]
    setPicks({ ...picks, [piece.id]: next })
    setError(undefined)
    if (!next.length) return  // nothing to save yet: the backend refuses an empty pick, the button waits for one
    try { await call('visuals.pick', { piece_id: piece.id, keys: next }) } catch (e) { setError(e as BackendError) }
  }

  async function confirm() {
    setStarting(true)
    setError(undefined)
    try {
      await call('jobs.start', { project_id: pieces[0].project_id, kind: 'visuals' })
      onStarted()
    } catch (e) { setError(e as BackendError) } finally { setStarting(false) }
  }

  return (
    <section aria-label="Choose the footage" className="glass anim-drift mb-8 grid gap-7 p-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="grid gap-1.5">
          <h2 className="font-display text-[22px] font-semibold tracking-[-0.02em]">Choose the footage</h2>
          <p className="max-w-[62ch] text-[13px] leading-relaxed text-ink-2">
            Nothing has been downloaded yet. The studio's picks are numbered in the order they play; click any shot to
            swap it. Only what you pick here is downloaded.
          </p>
        </div>
        <Button variant="primary" onClick={confirm} disabled={disabled || starting || !!missing.length || !total}>
          <DownloadSimple size={14} weight="bold" />{starting ? 'Starting' : `Download ${total} ${total === 1 ? 'shot' : 'shots'} and continue`}
        </Button>
      </div>
      {!!missing.length && (
        <p className="-mt-3 text-xs text-danger">Pick at least one shot for piece {missing.map((p) => String(p.idx).padStart(3, '0')).join(', ')}.</p>
      )}
      {error && <ErrorNote error={error} />}

      {pieces.map((p) => {
        const review = p.content.review!
        const mine = picks[p.id] ?? []
        return (
          <div key={p.id} className="grid gap-3 border-t border-line pt-6">
            <div className="flex items-baseline justify-between gap-4">
              <p className="min-w-0 truncate text-[14px] font-medium text-ink">
                <span className="tnum mr-3 font-display text-xs text-accent">{String(p.idx).padStart(3, '0')}</span>{p.content.quote.text}
              </p>
              <span className="tnum shrink-0 text-xs text-ink-3">{mine.length} of {review.want} {review.want === 1 ? 'shot' : 'shots'}</span>
            </div>
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-3">
              {review.options.map((o, i) => {
                const order = mine.indexOf(o.key)
                const on = order >= 0
                return (
                  <li key={o.key} className="anim-slot" style={{ '--i': Math.min(i, 12) } as CSSProperties}>
                    <button type="button" onClick={() => toggle(p, o.key)} aria-pressed={on}
                      title={`${o.candidate.creator || 'Unknown creator'} · ${o.queries.join(', ')}`}
                      className={cx('group relative block aspect-[9/16] w-full overflow-hidden rounded-[14px] bg-black/30 transition-[box-shadow,transform] duration-200',
                        on ? 'shadow-[0_0_0_2px_var(--color-accent),0_12px_28px_-12px_rgb(240_135_58/0.5)]'
                          : 'shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1)] hover:-translate-y-0.5')}>
                      <img src={mediaUrl(o.thumb)} alt={`Footage option by ${o.candidate.creator || 'unknown'}`} loading="lazy"
                        className={cx('absolute inset-0 size-full object-cover transition-opacity duration-200', !on && 'opacity-70 group-hover:opacity-100')} />
                      {on && (
                        <span className="tnum absolute left-2 top-2 grid size-6 place-items-center rounded-full bg-accent text-2xs font-semibold text-ground">{order + 1}</span>
                      )}
                      <span className="absolute inset-x-1.5 bottom-1.5 flex flex-wrap items-center gap-1">
                        {o.candidate.asset_type === 'video' && (
                          <span className="inline-flex items-center gap-0.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                            <Play size={7} weight="fill" />{Math.round(o.candidate.duration)}s
                          </span>
                        )}
                        {o.note && (
                          <span className="rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] text-ink-2">
                            {o.note === 'used' ? 'Used before' : 'Like recent footage'}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </section>
  )
}
