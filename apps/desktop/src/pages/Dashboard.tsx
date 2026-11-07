import type { CSSProperties } from 'react'
import { ArrowRight, Plus } from '@phosphor-icons/react'
import { FORMATS, formatDate, label, mediaUrl, useQuery, type Project } from '../lib/studio'
import { Button, ErrorNote, Reveal, cx } from '../components/ui'
import { Cover } from '../components/Cover'
import { projectState } from '../components/ProjectList'

type Stats = { projects: number; pieces: number; today: number; generating: number }

const at = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

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
  return parts.join(' ') || 'Everything you make is written, rendered and kept on this computer.'
}

function describe(p: Project) {
  const b = p.brief
  if (b.kind === 'clip') return `Clips from video, ${b.orientation}`
  const format = FORMATS.find((f) => f.value === b.format)?.label ?? b.format
  return `${label(b.tone)}, ${format.toLowerCase()}, ${plural(b.quantity, 'piece')}`
}

export function Dashboard({ onCreate, onOpen, onAll }: { onCreate: () => void; onOpen: (id: string) => void; onAll: () => void }) {
  const { data, error, reload } = useQuery<Project[]>('projects.list', { limit: 9 })
  const stats = useQuery<Stats>('app.stats').data
  const first = data?.length === 0
  const [latest, ...rest] = data ?? []

  return (
    <div className="grid gap-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="grid gap-2">
          <h1 className="font-display text-title font-semibold tracking-[-0.03em]"><Reveal text={greeting()} /></h1>
          <p className="anim-drift min-h-[1.5em] max-w-[60ch] text-[15px] text-ink-2" style={at(260)}>{summary(stats)}</p>
        </div>
        <div className="anim-drift" style={at(200)}>
          <Button variant="primary" onClick={onCreate} kbd="Ctrl N"><Plus size={14} weight="bold" />New project</Button>
        </div>
      </header>
      {error && <ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} />}

      {first && <Welcome onCreate={onCreate} />}
      {latest && <Continue project={latest} onOpen={() => onOpen(latest.id)} />}

      {latest && (
        <section className="grid gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-[17px] font-semibold tracking-[-0.015em]">Recent projects</h2>
            <Button variant="ghost" onClick={onAll}>All projects<ArrowRight size={13} /></Button>
          </div>
          {rest.length ? (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(172px,1fr))] gap-5">
              {rest.map((p, i) => (
                <li key={p.id} className="anim-slot" style={{ '--i': i + 4 } as CSSProperties}>
                  <button onClick={() => onOpen(p.id)} className="group grid w-full gap-3 rounded-[20px] text-left">
                    <Cover src={p.cover} quote={p.quote} className="transition-transform duration-300 ease-[var(--ease-premium)] group-hover:-translate-y-1" />
                    <span className="grid gap-0.5 px-1">
                      <span className="truncate text-[13px] font-medium text-ink">{p.name}</span>
                      <span className={cx('truncate text-xs', p.status === 'failed' ? 'text-danger' : p.status === 'generating' ? 'text-accent' : 'text-ink-3')}>
                        {projectState(p)} · {formatDate(p.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-ink-3">Your other projects collect here as you make them.</p>
          )}
        </section>
      )}
    </div>
  )
}

/** The latest project, front and centre: its real cover lights the card, with honest progress and one way in. */
function Continue({ project: p, onOpen }: { project: Project; onOpen: () => void }) {
  const total = p.brief.kind === 'clip' ? 0 : p.brief.quantity
  const bars = total ? [['Written', p.pieces_written ?? 0], ['Rendered', p.rendered ?? 0]] as const : []
  return (
    <section className="grid gap-4">
      <h2 className="font-display text-[17px] font-semibold tracking-[-0.015em]">Pick up where you left off</h2>
      <article className="glass relative isolate grid grid-cols-[auto_minmax(0,1fr)] items-center gap-10 overflow-hidden p-8 max-[900px]:grid-cols-1">
        {/* the cover itself, blurred huge behind the card: each project tints its own card */}
        {p.cover ? (
          <img aria-hidden src={mediaUrl(p.cover)} alt="" className="absolute inset-0 -z-10 size-full scale-125 object-cover opacity-25 blur-3xl" />
        ) : (
          <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(60%_90%_at_15%_20%,rgb(240_135_58/0.28),transparent_70%)]" />
        )}
        <Cover src={p.cover} quote={p.quote} size="lg" className="w-[230px] max-[900px]:w-[180px]" />
        <div className="grid gap-6">
          <div className="grid gap-2">
            <h3 className="font-display text-hero font-semibold tracking-[-0.035em] text-balance">
              <button onClick={onOpen} className="text-left transition-colors duration-200 hover:text-accent">
                <Reveal key={p.id} text={p.name} delay={220} step={70} />
              </button>
            </h3>
            <p className="anim-drift text-[13px] text-ink-3" style={at(420)}>{describe(p)} · {formatDate(p.created_at)}</p>
          </div>
          {!!bars.length && (
            <dl className="anim-drift grid max-w-[420px] gap-3" style={at(500)}>
              {bars.map(([k, v]) => (
                <div key={k} className="grid gap-1.5">
                  <div className="flex justify-between text-xs"><dt className="text-ink-2">{k}</dt><dd className="tnum text-ink-3">{v} / {total}</dd></div>
                  <div className="h-[3px] overflow-hidden rounded-full bg-white/[0.08]">
                    <div className="h-full origin-left rounded-full bg-accent transition-transform duration-700 ease-[var(--ease-premium)]"
                      style={{ transform: `scaleX(${Math.min(1, v / total)})` }} />
                  </div>
                </div>
              ))}
            </dl>
          )}
          <div className="anim-drift flex flex-wrap items-center gap-4" style={at(580)}>
            <Button variant="primary" onClick={onOpen}>Open project<ArrowRight size={13} /></Button>
            <span className={cx('text-[13px]', p.status === 'failed' ? 'text-danger' : p.status === 'generating' ? 'text-accent' : 'text-ink-2')}>
              {projectState(p)}
            </span>
          </div>
        </div>
      </article>
    </section>
  )
}

/** First run: what the studio does, in its three real stages, and the one button that starts it. */
function Welcome({ onCreate }: { onCreate: () => void }) {
  const steps = [
    ['Brief', 'Pick a topic and a genre. Every option has a working default.'],
    ['Write and render', 'The studio writes each piece, narrates it, finds footage and cuts the video.'],
    ['Export', 'Files and captions for every platform, ready to schedule.'],
  ] as const
  return (
    <section className="glass relative isolate grid gap-10 overflow-hidden p-10">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(70%_90%_at_85%_15%,rgb(240_135_58/0.3),transparent_65%),radial-gradient(50%_60%_at_10%_100%,rgb(150_96_120/0.18),transparent_70%)]" />
      <div className="grid max-w-[34rem] gap-5">
        <h2 className="font-display text-hero font-semibold tracking-[-0.035em]">
          <Reveal text="Your first batch starts here" delay={240} step={70} />
        </h2>
        <p className="anim-drift max-w-[44ch] text-[15px] leading-relaxed text-ink-2" style={at(520)}>
          Give it a topic and the studio plans distinct angles, then builds the visuals, narration and final renders for you.
        </p>
        <div className="anim-drift pt-1" style={at(600)}>
          <Button variant="primary" onClick={onCreate} kbd="Ctrl N"><Plus size={14} weight="bold" />Start your first project</Button>
        </div>
      </div>
      <ol className="grid grid-cols-3 gap-8 border-t border-line pt-8 max-[900px]:grid-cols-1">
        {steps.map(([t, d], i) => (
          <li key={t} className="anim-slot grid gap-2" style={{ '--i': i + 6 } as CSSProperties}>
            <span className="tnum font-display text-[13px] font-semibold text-accent">{String(i + 1).padStart(2, '0')}</span>
            <span className="text-[14px] font-medium text-ink">{t}</span>
            <span className="text-[13px] leading-relaxed text-ink-3">{d}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
