import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { ArrowRight, Plus } from '@phosphor-icons/react'
import { formatDate, mediaUrl, useBusy, useQuery, type Project } from '../lib/studio'
import { Button, ErrorNote, Reveal, cx, spot } from '../components/ui'
import { Cover } from '../components/Cover'
import { projectState } from '../components/ProjectList'

type Stats = { projects: number; pieces: number; today: number; generating: number }
// one piece in the crowd: its newest rendered image, or none yet (a draft: shown as its own words on a lit frame)
type Showpiece = { id: string; quote: string; status: string; project_id: string; project: string; image: string | null }

const at = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
// renders the studio's own design engine made, bundled: they fill the crowd until the user has seven of their own
const SAMPLES = Object.values(import.meta.glob('../assets/splash/card-*.webp', { eager: true, import: 'default' })) as string[]

function greeting(now = new Date()) {
  const h = now.getHours()
  return h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

/** One honest sentence about the studio right now, from real counts: what is running, what landed today. */
function summary(s?: Stats) {
  if (!s) return ''
  const parts = []
  if (s.generating) parts.push(`${plural(s.generating, 'project')} ${s.generating === 1 ? 'is' : 'are'} generating right now.`)
  if (s.today) parts.push(`${plural(s.today, 'piece')} written today.`)
  if (!parts.length && s.projects) parts.push(`${plural(s.pieces, 'piece')} across ${plural(s.projects, 'project')} so far.`)
  return parts.join(' ') || 'Quote images, narrated videos and clips, written, rendered and kept on this computer.'
}

// The crowd, like a group selfie: the newest work biggest and nearest in the middle, the rest stepping down and
// leaning in toward it. Everything is measured in cqh, the height of the room left under the buttons, so the crowd
// can never grow into the text (a width-based layout covered the buttons on wide windows) and on a wide window it
// spreads sideways instead. o = centre offset from the middle, w = width, y = sink below the edge (% of the tile's
// own height), r = tilt. Tiles are 4:5, so the middle one (w 76) stands 95cqh tall and sinks 5%.
// offsets = the two half-widths + a 4cqh gap, so neighbours never overlap (owner report 2026-11-08); the tilt
// grows outward, so the gaps open toward the top instead of closing
const SLOTS = [
  { o: -189, w: 50, y: 0, r: -10 }, { o: -132, w: 56, y: 3, r: -6 }, { o: -70, w: 61, y: 5, r: -3 },
  { o: 0, w: 71, y: 5, r: 0 },
  { o: 70, w: 61, y: 5, r: 3 }, { o: 132, w: 56, y: 3, r: 6 }, { o: 189, w: 50, y: 0, r: 10 },
]
const PROMINENCE = [3, 2, 4, 1, 5, 0, 6]  // newest work goes front and centre, then outward

export function Dashboard({ onCreate, onOpen, onAll }: { onCreate: () => void; onOpen: (id: string) => void; onAll: () => void }) {
  // everything reloads when a job finishes, so content generated or rendered while you sit here shows up
  const busy = useBusy()
  const [finished, setFinished] = useState(0)
  const wasBusy = useRef(busy)
  useEffect(() => { if (wasBusy.current && !busy) setFinished((n) => n + 1); wasBusy.current = busy }, [busy])
  const { data, error, reload } = useQuery<Project[]>('projects.list', { limit: 9 }, finished)
  const stats = useQuery<Stats>('app.stats', undefined, finished).data
  const pieces = useQuery<Showpiece[]>('pieces.showcase', { limit: 7 }, finished).data
  const first = data?.length === 0
  const latest = data?.[0]

  return (
    <div className="grid gap-12">
      <Hero latest={latest} pieces={pieces} summary={summary(stats)} onCreate={onCreate} onOpen={onOpen} first={first} />
      {error && <ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} />}

      {first && <FirstSteps />}

      {!!data?.length && (
        <section className="grid gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-[17px] font-semibold tracking-[-0.015em]">Recent projects</h2>
            <Button variant="ghost" onClick={onAll}>All projects<ArrowRight size={13} /></Button>
          </div>
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(172px,1fr))] gap-5">
            {data.map((p, i) => (
              <li key={p.id} className="anim-slot" style={{ '--i': i + 4 } as CSSProperties}>
                <button onClick={() => onOpen(p.id)} className="group grid w-full gap-3 rounded-[20px] text-left">
                  <Cover src={p.cover} quote={p.quote} className="transition-transform duration-300 ease-[var(--ease-premium)] group-hover:-translate-y-1" />
                  <span className="grid gap-0.5 px-1">
                    <span className="truncate text-[13px] font-medium text-ink">{p.name}</span>
                    <span className={cx('truncate text-xs', p.status === 'failed' ? 'text-danger' : p.status === 'generating' ? 'text-accent-ink' : 'text-ink-3')}>
                      {projectState(p)} · {formatDate(p.created_at)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/** The landing card: a centred two-line headline, one honest sentence, two ways in, and the user's own work
 *  rising out of the bottom edge as a crowd of covers. */
function Hero({ latest, pieces, summary, onCreate, onOpen, first }: {
  latest?: Project; pieces?: Showpiece[]; summary: string; onCreate: () => void; onOpen: (id: string) => void; first?: boolean
}) {
  // the newest pieces, rendered or not: fresh content shows the moment it is written, as a labelled draft until it
  // renders (a deleted render turns its piece back into a draft, never a fake finished post)
  const own = (pieces ?? []).slice(0, SLOTS.length)
  const tiles: ({ kind: 'piece'; p: Showpiece } | { kind: 'sample'; src: string })[] = [
    ...own.map((p) => ({ kind: 'piece' as const, p })),
    ...SAMPLES.slice(0, Math.max(0, SLOTS.length - own.length)).map((src) => ({ kind: 'sample' as const, src })),  // 8 bundled: never a repeat
  ]
  const placed = PROMINENCE.slice(0, tiles.length).map((slot, rank) => ({ slot, tile: tiles[rank], rank }))

  return (
    <section className="glass relative isolate flex h-[min(calc(100dvh-150px),780px)] min-h-[600px] flex-col items-center overflow-hidden px-10 pt-16 text-center">
      <h1 className="max-w-[22ch] font-display text-hero font-semibold tracking-[-0.035em] text-balance">
        <Reveal text={`${greeting()},`} delay={120} step={70} />
        <br />
        <Reveal text="what are we" delay={300} step={70} />{' '}
        <Reveal text="making" delay={510} step={70} className="text-pop" />{' '}
        <Reveal text="today?" delay={580} step={70} />
      </h1>
      <p className="anim-drift mt-5 min-h-[1.5em] max-w-[52ch] text-[15px] leading-relaxed text-ink-2" style={at(560)}>{summary}</p>
      <div className="anim-drift mt-7 flex flex-wrap items-center justify-center gap-3" style={at(640)}>
        <Button variant="primary" onClick={onCreate} kbd="Ctrl N"><Plus size={14} weight="bold" />{first ? 'Start your first project' : 'New project'}</Button>
        {latest && (
          <Button onClick={() => onOpen(latest.id)} className="pl-2">
            {latest.cover
              ? <img src={mediaUrl(latest.cover)} alt="" className="size-6 rounded-full object-cover" />
              : <span aria-hidden className="size-6 rounded-full bg-accent" />}
            <span className="max-w-[22ch] truncate">Pick up {latest.name}</span>
          </Button>
        )}
      </div>

      {/* the crowd: each tile is positioned and tilted by its slot, rises in on its own beat, and lifts on hover */}
      <div className="pointer-events-none relative -mx-10 mt-10 min-h-0 flex-1 self-stretch [container-type:size]">
        {placed.map(({ slot, tile, rank }) => {
          const s = SLOTS[slot]
          const z = 10 - Math.abs(slot - 3)
          const face = tile.kind === 'piece' ? (
            <div className="relative">
              <Cover src={tile.p.image} quote={tile.p.quote} className="w-full" />
              {!tile.p.image && (
                <span className="absolute left-3 top-3 rounded-full bg-black/55 px-2.5 py-1 text-2xs font-medium text-white backdrop-blur-sm">Draft</span>
              )}
            </div>
          )
            : <img src={tile.src} alt="" className="aspect-[4/5] w-full rounded-[18px] object-cover shadow-[0_18px_40px_-16px_rgb(17_18_20/0.22),inset_0_0_0_1px_rgb(17_18_20/0.1)]" />
          return (
            <div key={slot} className="absolute bottom-0" style={{ left: `calc(50% + ${s.o}cqh)`, width: `${s.w}cqh`, zIndex: z,
              transform: `translate(-50%, ${s.y}%) rotate(${s.r}deg)`, transformOrigin: '50% 100%' }}>
              <div className="anim-slot" style={{ '--i': rank + 6 } as CSSProperties}>
                {tile.kind === 'piece' ? (
                  <button onClick={() => onOpen(tile.p.project_id)} title={tile.p.project} aria-label={`Open ${tile.p.project}`}
                    className="group pointer-events-auto block w-full rounded-[18px] transition-transform duration-300 ease-[var(--ease-premium)] hover:-translate-y-3">
                    {face}
                  </button>
                ) : (
                  <div aria-hidden className="opacity-90">{face}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {/* the card's floor: the crowd fades into the glass instead of ending on a hard line */}
    </section>
  )
}

/** First run: the three real stages, under the hero. */
function FirstSteps() {
  const steps = [
    ['Choose what to make', 'Quote images, narrated videos or clips from a long video. Every option has a working default.'],
    ['Write and render', 'The studio writes each piece, finds the visuals, designs or cuts it, and renders the files.'],
    ['Export', 'Files and captions for every platform, ready to schedule.'],
  ] as const
  return (
    <ol className="grid grid-cols-3 gap-8 max-[900px]:grid-cols-1">
      {steps.map(([t, d], i) => (
        <li key={t} className="anim-slot grid gap-2" style={{ '--i': i + 10 } as CSSProperties}>
          <span className="tnum font-display text-[13px] font-semibold text-accent-ink">{String(i + 1).padStart(2, '0')}</span>
          <span className="text-[14px] font-medium text-ink">{t}</span>
          <span className="text-[13px] leading-relaxed text-ink-3">{d}</span>
        </li>
      ))}
    </ol>
  )
}
