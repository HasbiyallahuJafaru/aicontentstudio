// The piece preview (PRD §40-41): native video controls for playback, fit/actual for images, a
// before/after look at the design, and per-component regeneration (§43) with approval.
import { useEffect, useState } from 'react'
import { ArrowClockwise, Check, Export, X } from '@phosphor-icons/react'
import { call, label, mediaUrl, useQuery, type Asset, type Piece, type Render, type VoiceList } from '../lib/studio'
import { Button, ErrorNote, Select, cx } from './ui'

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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

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
    <div role="dialog" aria-label={`Preview ${piece.idx}`} onClick={onClose}
      className="fixed inset-0 z-40 grid place-items-center bg-black/70 p-6 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="grid max-h-full w-full max-w-[820px] gap-5 overflow-y-auto rounded-[24px] bg-[#17181a] p-8 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.09),0_32px_80px_-24px_rgb(0_0_0/0.8)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-ink-3">{label(piece.angle)}</p>
            <h2 className="mt-0.5 font-display text-[20px] font-semibold tracking-[-0.02em]">{piece.quote}</h2>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {piece.status !== 'written' && (
              <span className="rounded-full bg-white/[0.07] px-3 py-1 text-2xs font-medium text-ink-2">{label(piece.status)}</span>
            )}
            <Button variant="ghost" onClick={onClose} aria-label="Close preview"><X size={15} /></Button>
          </div>
        </div>

        {video ? (
          <div className="grid justify-items-center gap-2">
            <video src={mediaUrl(video.local_path)} controls className="max-h-[56vh] rounded-field" />
            <p className="tnum text-2xs text-ink-3">
              MP4 · H.264{video.width && video.height ? ` · ${video.width} × ${video.height}` : ''}
              {video.fps ? ` · ${Math.round(video.fps)} FPS` : ''}
              {video.duration ? ` · ${video.duration.toFixed(1)}s` : ''}
            </p>
          </div>
        ) : image && (
          <div className="grid justify-items-center gap-2">
            <img src={mediaUrl(view === 'after' ? image.local_path : thumb ?? image.local_path)} alt="Rendered piece"
              className={cx('rounded-field', actual ? 'max-w-none' : 'max-h-[56vh]')} />
            <div className="flex gap-1.5">
              <Button variant="ghost" onClick={() => setActual(false)} className={cx(!actual && 'text-ink')}>Fit</Button>
              <Button variant="ghost" onClick={() => setActual(true)} className={cx(actual && 'text-ink')}>Actual</Button>
              {thumb && <>
                <Button variant="ghost" onClick={() => setView('after')} className={cx(view === 'after' && 'text-ink')}>After</Button>
                <Button variant="ghost" onClick={() => setView('before')} className={cx(view === 'before' && 'text-ink')}>Before</Button>
              </>}
            </div>
          </div>
        )}

        {error && <ErrorNote error={error} />}

        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="grid gap-3">
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
            <div className="grid gap-1">
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
          <div className="flex items-center gap-2">
            <Button disabled={busy !== null} onClick={exportPiece}>
              <Export size={14} />{busy === 'export' ? 'Exporting…' : 'Export this piece'}
            </Button>
            {piece.status === 'ready' && (
              <Button variant="primary" disabled={busy !== null} onClick={approve}>
                <Check size={14} weight="bold" />{busy === 'approve' ? 'Approving…' : 'Approve'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
