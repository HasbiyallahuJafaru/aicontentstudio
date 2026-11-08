import { useState, type ComponentType, type CSSProperties } from 'react'
import { Images, PlusCircle, Trash } from '@phosphor-icons/react'
import { call, label, mediaUrl, useQuery, BackendError, type Asset } from '../lib/studio'
import { Button, Choices, ErrorNote, PageHeader } from '../components/ui'
import MasonryGrid from '../components/Masonry'

// typed loosely: the vendored file is untyped (its `items = []` default would infer never[])
const Masonry = MasonryGrid as unknown as ComponentType<Record<string, unknown>>

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
          <span className="grid size-11 place-items-center rounded-2xl bg-accent/15 text-accent-ink"><Images size={20} /></span>
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
            : <Masonry items={assets.map(tile)} columnWidth={220} gap={16} radius={18} captions="always"
                hoverEffect="zoom" animateFrom="bottom" draggable={false} lightbox
                renderAction={(item: { id: string }) => {
                  const a = assets.find((x) => x.id === item.id)!
                  return (
                    <span className="flex items-center gap-1.5">
                      <button onClick={() => remove(a)} aria-label={`Delete this ${a.asset_type} from the library`} title="Delete from the library"
                        data-reveal className="grid size-8 place-items-center rounded-full bg-ink text-white transition-colors duration-150 hover:bg-danger">
                        <Trash size={14} />
                      </button>
                      {a.dominant_colors.slice(0, 3).map((c) => (
                        <span key={c} title={c} className="size-3.5 rounded-full shadow-[0_0_0_2px_#fff]" style={{ backgroundColor: c }} />
                      ))}
                    </span>
                  )
                }} />}
        </>
      )}
    </>
  )
}

/** One masonry tile per downloaded visual: its real aspect, its facts in the caption; clicking opens the full-screen
 * carousel (arrows, Escape). Videos show their poster frame. */
function tile(a: Asset) {
  const kind = a.asset_type === 'video' ? `${Math.round(a.duration)}s video${a.fps >= 59 ? ', 60 FPS' : ''}` : 'Image'
  const used = a.times_used === 0 ? 'Never used' : `Used ${a.times_used} ${a.times_used === 1 ? 'time' : 'times'}`
  return { id: a.id, img: mediaUrl(a.thumb_path), width: a.width, height: a.height,
    title: `${label(a.provider)} · ${label(a.asset_type)}`,
    description: `${a.width} × ${a.height}, ${kind}. ${used}.${a.creator ? ` By ${a.creator}.` : ''}`,
    alt: a.creator ? `Visual by ${a.creator}` : 'Downloaded visual' }
}
