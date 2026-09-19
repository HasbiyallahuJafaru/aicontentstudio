import { useState } from 'react'
import { Play, PlusCircle } from '@phosphor-icons/react'
import { formatDate, label, mediaUrl, useQuery, type Asset } from '../lib/studio'
import { Button, Choices, ErrorNote, PageHeader, cx } from '../components/ui'

// ponytail: filters run client-side over the full list; move to the query when a library gets big enough to lag.
type Usage = 'all' | 'never' | 'recent'

const RECENT_DAYS = 7

function recentlyUsed(a: Asset) {
  if (!a.last_used_at) return false
  return Date.now() - new Date(a.last_used_at).getTime() < RECENT_DAYS * 86_400_000
}

export function Library({ onCreate }: { onCreate: () => void }) {
  const { data, error, reload } = useQuery<Asset[]>('assets.list')
  const [type, setType] = useState<'all' | 'image' | 'video'>('all')
  const [provider, setProvider] = useState<'all' | 'pexels' | 'unsplash'>('all')
  const [usage, setUsage] = useState<Usage>('all')

  const assets = (data ?? []).filter((a) => (type === 'all' || a.asset_type === type)
    && (provider === 'all' || a.provider === provider)
    && (usage === 'all' || (usage === 'never' ? a.times_used === 0 : recentlyUsed(a))))

  return (
    <>
      <PageHeader title="Library">
        {data && <span className="text-xs text-ink-3">{data.length} downloaded {data.length === 1 ? 'asset' : 'assets'}</span>}
        {error && <Button onClick={reload}>Try again</Button>}
      </PageHeader>
      {error && <div className="mb-6"><ErrorNote error={error} /></div>}

      {data && data.length === 0 && (
        <section className="grid max-w-md gap-3 py-12">
          <h2 className="text-base font-semibold">No assets yet</h2>
          <p className="text-ink-2">
            Visuals downloaded for your projects land here. Generate a project with a Pexels or Unsplash key set in Settings.
          </p>
          <div><Button variant="primary" onClick={onCreate}><PlusCircle size={15} />Create a project</Button></div>
        </section>
      )}

      {data && data.length > 0 && (
        <>
          <div className="mb-6 flex flex-wrap items-start gap-x-10 gap-y-4">
            <Choices legend="Type" options={[{ value: 'all', label: 'All' }, { value: 'image', label: 'Images' },
              { value: 'video', label: 'Videos' }]} value={type} onChange={setType} />
            <Choices legend="Provider" options={[{ value: 'all', label: 'All' }, { value: 'pexels', label: 'Pexels' },
              { value: 'unsplash', label: 'Unsplash' }]} value={provider} onChange={setProvider} />
            <Choices legend="Usage" options={[{ value: 'all', label: 'All' }, { value: 'never', label: 'Never used' },
              { value: 'recent', label: 'Recently used' }]} value={usage} onChange={setUsage} />
          </div>
          {assets.length === 0
            ? <p className="py-12 text-[13px] text-ink-3">No assets match these filters.</p>
            : <ul className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4">
                {assets.map((a) => <AssetCard key={a.id} asset={a} />)}
              </ul>}
        </>
      )}
    </>
  )
}

function AssetCard({ asset: a }: { asset: Asset }) {
  return (
    <li className="overflow-hidden rounded-field bg-white/[0.03] shadow-[inset_0_0_0_1px_rgb(255_244_232/0.06)]">
      <div className="relative aspect-[3/4] bg-black/30">
        <img src={mediaUrl(a.thumb_path)} alt={a.creator ? `Visual by ${a.creator}` : 'Downloaded visual'}
          loading="lazy" className="size-full object-cover" />
        {a.asset_type === 'video' && (
          <span className={cx('absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/65 px-2 py-0.5',
            'text-2xs text-white')}>
            <Play size={9} weight="fill" />{Math.round(a.duration)}s{a.fps >= 59 && ' · 60 FPS'}
          </span>
        )}
      </div>
      <div className="grid gap-0.5 px-3.5 py-3 text-xs">
        <p className="text-ink">{label(a.provider)} · {label(a.asset_type)}</p>
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
