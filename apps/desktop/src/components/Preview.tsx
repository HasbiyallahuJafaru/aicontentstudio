// The piece preview (PRD §40-41): native video controls for playback, fit/actual for images, a
// before/after look at the design, and per-component regeneration (§43) with approval.
// Layout: a media stage that fills the panel height beside a fixed rail, so the render and every
// control are on screen at once. Only the rail's middle band ever scrolls.
import { useState } from 'react'
import { ArrowClockwise, Check, Export, X } from '@phosphor-icons/react'
import { call, label, mediaUrl, useQuery, type Asset, type Piece, type Render, type VoiceList } from '../lib/studio'
import { Button, Dialog, ErrorNote, Select, cx } from './ui'

const SCOPES = ['quote', 'narration', 'visual', 'design'] as const
type Scope = (typeof SCOPES)[number]

export function Preview({ piece, renders, assets, voice, onClose, onChanged }: {
  piece: Piece
  renders: Render[]
  assets: Asset[]
  voice?: string
  onClose: () => void
  onChanged: () => void
}) {
  const { data: voices } = useQuery<VoiceList>('tts.voices')
  const video = renders.find((r) => r.kind === 'video')
  const image = renders.find((r) => r.kind === 'image')
  const thumb = assets.find((a) => a.id === piece.content.asset?.id)?.thumb_path
  const [view, setView] = useState<'after' | 'before'>('after')
  const [actual, setActual] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<Error>()

  async function run(action: string, fn: () => Promise<unknown>) {
    setBusy(action)
    setError(undefined)
    try {
      await fn()
      onChanged()
      onClose()
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(null)
    }
  }

  const regenerate = (scope: Scope) =>
    run(scope, () => call('pieces.regenerate', { piece_id: piece.id, scope }))
  const approve = () => run('approve', () => call('pieces.approve', { piece_id: piece.id }))
  const exportPiece = () =>
    run('export', () => call('jobs.start', { project_id: piece.project_id, kind: 'export', piece_ids: [piece.id] }))

  return (
    <Dialog label={`Preview ${piece.idx}`} width={1180} onClose={onClose}
      className="h-[min(780px,calc(100dvh-3rem))] grid-cols-[minmax(0,1fr)_368px] max-[1040px]:h-[calc(100dvh-3rem)] max-[1040px]:grid-cols-1 max-[1040px]:grid-rows-[minmax(0,1fr)_auto]">
      <section className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-2 p-3">
        <div className="grid min-h-0 place-items-center overflow-auto rounded-field bg-black/35">
          {video ? (
            <video src={mediaUrl(video.local_path)} controls className="max-h-full max-w-full rounded-[10px]" />
          ) : image ? (
            <img src={mediaUrl(view === 'after' ? image.local_path : thumb ?? image.local_path)} alt="Rendered piece"
              className={cx('rounded-[10px]', actual ? 'max-w-none' : 'max-h-full max-w-full')} />
          ) : (
            <p className="p-8 text-[13px] text-ink-3">Nothing rendered for this piece yet.</p>
          )}
        </div>
        <div className="flex min-h-9 flex-wrap items-center justify-center gap-x-4 gap-y-1">
          {video && (
            <p className="tnum text-2xs text-ink-3">
              MP4 · H.264{video.width && video.height ? ` · ${video.width} × ${video.height}` : ''}
              {video.fps ? ` · ${Math.round(video.fps)} FPS` : ''}
              {video.duration ? ` · ${video.duration.toFixed(1)}s` : ''}
            </p>
          )}
          {image && !video && (
            <div className="flex gap-1.5">
              <Button variant="ghost" onClick={() => setActual(false)} className={cx(!actual && 'text-ink')}>Fit</Button>
              <Button variant="ghost" onClick={() => setActual(true)} className={cx(actual && 'text-ink')}>Actual</Button>
              {thumb && <>
                <Button variant="ghost" onClick={() => setView('after')} className={cx(view === 'after' && 'text-ink')}>After</Button>
                <Button variant="ghost" onClick={() => setView('before')} className={cx(view === 'before' && 'text-ink')}>Before</Button>
              </>}
            </div>
          )}
        </div>
      </section>

      <aside className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] border-l border-line max-[1040px]:border-l-0 max-[1040px]:border-t">
        <header className="grid gap-2 border-b border-line px-6 py-5">
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs text-ink-3">{label(piece.angle)}</p>
            <Button variant="ghost" onClick={onClose} aria-label="Close preview" className="-mt-2 -mr-3 h-8"><X size={15} /></Button>
          </div>
          <h2 className="line-clamp-3 font-display text-[17px] font-semibold leading-snug tracking-[-0.02em]">{piece.quote}</h2>
          {piece.status !== 'written' && (
            <span className="w-fit rounded-full bg-white/[0.07] px-3 py-1 text-2xs font-medium text-ink-2">{label(piece.status)}</span>
          )}
        </header>

        {/* The one scroll region. Dropdowns inside it need the clip lifted while open, same trick as .glass. */}
        <div className="grid content-start gap-5 overflow-y-auto px-6 py-5 has-[[aria-expanded=true]]:overflow-visible">
          {error && <ErrorNote error={error} />}
          <div className="grid gap-1.5">
            <p className="text-[13px] font-medium text-ink">Redo one part</p>
            <div className="flex flex-wrap gap-1.5">
              {SCOPES.map((s) => (
                <Button key={s} variant="ghost" disabled={busy !== null} onClick={() => regenerate(s)}>
                  <ArrowClockwise size={13} />{busy === s ? 'Redoing…' : label(s)}
                </Button>
              ))}
            </div>
          </div>
          <div className="grid gap-1.5">
            <p className="text-[13px] font-medium text-ink">Narration voice</p>
            <Select value={voice ?? ''} disabled={busy !== null}
              onChange={(v) => run('voice', async () => {
                await call('projects.set_voice', { project_id: piece.project_id, voice: v })
                await call('jobs.start', { project_id: piece.project_id, kind: 'render', piece_ids: [piece.id] })
              })}
              options={[
                { value: '', label: 'Studio default (Settings)' },
                ...(voices?.kokoro ?? []).map((v) => ({ value: `kokoro:${v}`, label: `Kokoro · ${v}` })),
                ...(voices?.windows ?? []).map((v) => ({ value: `windows:${v}`, label: `Windows · ${v}` })),
              ]} />
            <p className="text-2xs text-ink-3">Swapping re-renders this piece's video with the new voice.</p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-line px-6 py-4">
          <Button disabled={busy !== null} onClick={exportPiece}>
            <Export size={14} />{busy === 'export' ? 'Exporting…' : 'Export'}
          </Button>
          {piece.status === 'ready' && (
            <Button variant="primary" disabled={busy !== null} onClick={approve}>
              <Check size={14} weight="bold" />{busy === 'approve' ? 'Approving…' : 'Approve'}
            </Button>
          )}
        </div>
      </aside>
    </Dialog>
  )
}
