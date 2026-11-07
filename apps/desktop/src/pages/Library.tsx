import { useState, type CSSProperties } from 'react'
import { Images, Play, PlusCircle, Trash } from '@phosphor-icons/react'
import { call, formatDate, label, mediaUrl, useQuery, BackendError, type Asset } from '../lib/studio'
import { Button, Choices, ErrorNote, PageHeader, cx } from '../components/ui'

// ponytail: filters run client-side over the full list; move to the query when a library gets big enough to lag.
type Usage = 'all' | 'never' | 'recent'

const RECENT_DAYS = 7
const HIGH_QUALITY = 0.6 // matches the technical quality score the analyser stores per asset

function recentlyUsed(a: Asset) {
  if (!a.last_used_at) return false
  return Date.now() - new Date(a.last_used_at).getTime() < RECENT_DAYS * 86_400_000
}

export function Library({ onCreate }: { onCreate: () => void }) {
  const { data, error, reload } = useQuery<Asset[]>('assets.list')
  const [type, setType] = useState<'all' | 'image' | 'video'>('all')
  const [provider, setProvider] = useState<'all' | 'pexels' | 'unsplash'>('all')
  const [usage, setUsage] = useState<Usage>('all')
  const [quality, setQuality] = useState<'all' | 'high'>('all')
  const [deleteError, setDeleteError] = useState<BackendError>()

  async function remove(a: Asset) {
    const used = a.times_used ? ` It was used ${a.times_used} ${a.times_used === 1 ? 'time' : 'times'}; finished renders keep it, pieces not yet rendered will need new footage.` : ''
    if (!confirm(`Delete this ${a.asset_type} from the library and from disk?${used}`)) return
    setDeleteError(undefined)
    try { await call('assets.delete', { asset_id: a.id }); reload() } catch (e) { setDeleteError(e as BackendError) }
  }

  const assets = (data ?? []).filter((a) => (type === 'all' || a.asset_type === type)
    && (provider === 'all' || a.provider === provider)
    && (usage === 'all' || (usage === 'never' ? a.times_used === 0 : recentlyUsed(a)))
    && (quality === 'all' || (a.quality_score ?? 0) >= HIGH_QUALITY))

  return (
    <>
      <PageHeader title="Library">
        {data && <span className="text-xs text-ink-3">{data.length} downloaded {data.length === 1 ? 'asset' : 'assets'}</span>}
        {error && <Button onClick={reload}>Try again</Button>}
      </PageHeader>
      {error && <div className="mb-6"><ErrorNote error={error} /></div>}
      {deleteError && <div className="mb-6"><ErrorNote error={deleteError} /></div>}

      {data && data.length === 0 && (
        <section className="glass anim-drift relative isolate grid max-w-xl gap-4 overflow-hidden p-9">
          <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(70%_80%_at_90%_10%,rgb(240_135_58/0.22),transparent_70%)]" />
          <span className="grid size-11 place-items-center rounded-2xl bg-accent/15 text-accent"><Images size={20} /></span>
          <h2 className="font-display text-[20px] font-semibold tracking-[-0.02em]">No assets yet</h2>
          <p className="max-w-[46ch] text-[14px] leading-relaxed text-ink-2">
            Visuals downloaded for your projects land here. Generate a project with a Pexels or Unsplash key set in Settings.
          </p>
          <div><Button variant="primary" onClick={onCreate}><PlusCircle size={15} />Create a project</Button></div>
        </section>
      )}

      {data && data.length > 0 && (
        <>
          <div className="glass anim-drift mb-7 flex flex-wrap items-start gap-x-10 gap-y-4 px-7 py-5" style={{ '--d': '160ms' } as CSSProperties}>
            <Choices legend="Type" options={[{ value: 'all', label: 'All' }, { value: 'image', label: 'Images' },
              { value: 'video', label: 'Videos' }]} value={type} onChange={setType} />
            <Choices legend="Provider" options={[{ value: 'all', label: 'All' }, { value: 'pexels', label: 'Pexels' },
              { value: 'unsplash', label: 'Unsplash' }]} value={provider} onChange={setProvider} />
            <Choices legend="Usage" options={[{ value: 'all', label: 'All' }, { value: 'never', label: 'Never used' },
              { value: 'recent', label: 'Recently used' }]} value={usage} onChange={setUsage} />
            <Choices legend="Quality" options={[{ value: 'all', label: 'All' }, { value: 'high', label: 'High' }]}
              value={quality} onChange={setQuality} />
          </div>
          {assets.length === 0
            ? <p className="py-12 text-[13px] text-ink-3">No assets match these filters.</p>
            : <ul className="grid grid-cols-[repeat(auto-fill,minmax(184px,1fr))] gap-5">
                {assets.map((a, i) => <AssetCard key={a.id} asset={a} i={i} onDelete={() => remove(a)} />)}
              </ul>}
        </>
      )}
    </>
  )
}

/** A downloaded visual, full bleed: its facts sit on the picture, its palette in the corner. */
function AssetCard({ asset: a, i, onDelete }: { asset: Asset; i: number; onDelete: () => void }) {
  return (
    <li className="anim-slot group relative isolate aspect-[3/4] overflow-hidden rounded-[18px] bg-black/30 shadow-[0_18px_40px_-18px_rgb(10_5_2/0.8),inset_0_0_0_1px_rgb(255_244_232/0.08)]"
      style={{ '--i': Math.min(i, 14) } as CSSProperties}>
      <img src={mediaUrl(a.thumb_path)} alt={a.creator ? `Visual by ${a.creator}` : 'Downloaded visual'} loading="lazy"
        className="absolute inset-0 -z-10 size-full object-cover transition-transform duration-700 ease-[var(--ease-premium)] group-hover:scale-[1.05]" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,transparent_45%,rgb(13_12_11/0.92))]" />
      <div className="absolute inset-x-3 top-3 flex items-center justify-between gap-2">
        {a.asset_type === 'video' ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-0.5 text-2xs text-white backdrop-blur">
            <Play size={9} weight="fill" />{Math.round(a.duration)}s{a.fps >= 59 && ' · 60 FPS'}
          </span>
        ) : <span className="rounded-full bg-black/55 px-2 py-0.5 text-2xs text-white backdrop-blur">Image</span>}
        <span className="flex items-center gap-1">
          <button onClick={onDelete} aria-label={`Delete this ${a.asset_type} from the library`} title="Delete from the library"
            className="mr-1 grid size-7 place-items-center rounded-full bg-black/55 text-ink-2 opacity-0 backdrop-blur transition-opacity duration-150 hover:bg-danger/80 hover:text-white focus-visible:opacity-100 group-hover:opacity-100">
            <Trash size={13} />
          </button>
          {a.dominant_colors.slice(0, 3).map((c) => (
            <span key={c} title={c} className="size-3 rounded-full shadow-[0_0_0_1.5px_rgb(13_12_11/0.6)]" style={{ backgroundColor: c }} />
          ))}
        </span>
      </div>
      <div className="absolute inset-x-0 bottom-0 grid gap-0.5 p-3.5 text-xs">
        <p className="font-medium text-ink">{label(a.provider)} · {label(a.asset_type)}</p>
        <p className="tnum text-ink-2">{a.width} × {a.height}</p>
        {a.creator && <p className="truncate text-ink-3" title={a.creator}>{a.creator}</p>}
        <p className="text-ink-3">
          {a.times_used === 0 ? 'Never used' : `Used ${a.times_used} ${a.times_used === 1 ? 'time' : 'times'}`}
          {a.last_used_at && ` · ${formatDate(a.last_used_at)}`}
        </p>
      </div>
    </li>
  )
}
