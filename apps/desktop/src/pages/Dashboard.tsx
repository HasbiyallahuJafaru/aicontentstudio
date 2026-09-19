import { ArrowRight, Plus } from '@phosphor-icons/react'
import { useQuery, type Project } from '../lib/studio'
import { Button, ErrorNote, cx } from '../components/ui'
import { ProjectList } from '../components/ProjectList'

type Stats = { projects: number; pieces: number; today: number; generating: number }
type Recent = { id: string; quote: string; project_id: string; project: string }

export function Dashboard({ onCreate, onOpen, onAll }: { onCreate: () => void; onOpen: (id: string) => void; onAll: () => void }) {
  const { data, error, reload } = useQuery<Project[]>('projects.list', { limit: 6 })
  const stats = useQuery<Stats>('app.stats').data
  const recent = useQuery<Recent[]>('pieces.recent', { limit: 3 }).data
  const first = data?.length === 0

  return (
    <div className="grid gap-5">
      <h1 className="pb-3 font-display text-title font-semibold tracking-[-0.03em]">Studio</h1>
      {error && <ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} />}

      <div className="grid grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)] gap-5 max-[1180px]:grid-cols-1">
        <section className="glass relative isolate overflow-hidden p-9 pb-7">
          <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(70%_90%_at_85%_15%,rgb(240_135_58/0.32),transparent_65%),radial-gradient(50%_60%_at_10%_100%,rgb(150_96_120/0.18),transparent_70%)]" />
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-8">
            <div className="grid max-w-[30rem] gap-5">
              <h2 className="font-display text-hero font-semibold tracking-[-0.035em]">
                {first ? 'Your first batch starts here' : 'Make the next batch'}
              </h2>
              <p className="max-w-[40ch] text-[15px] leading-relaxed text-ink-2">
                {first ? "Create a content batch and we'll build the visuals, narration and final renders for you."
                  : 'Pick a theme and a tone. The studio plans distinct angles and writes every piece.'}
              </p>
              <div className="pt-2"><Button variant="primary" onClick={onCreate} kbd="Ctrl N"><Plus size={14} weight="bold" />New project</Button></div>
            </div>
            <QuoteStack quotes={recent ?? []} />
          </div>

          <dl className="mt-9 grid grid-cols-4 gap-2 rounded-[20px] bg-black/25 p-2 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.06)]">
            {([['Projects', stats?.projects], ['Pieces written', stats?.pieces], ['Written today', stats?.today], ['Generating', stats?.generating]] as const)
              .map(([k, v]) => (
                <div key={k} className="grid gap-1 rounded-[14px] px-4 py-3">
                  <dd className={cx('tnum font-display text-[28px] leading-none font-semibold tracking-[-0.03em]', k === 'Generating' && !!v && 'text-accent')}>{v ?? 0}</dd>
                  <dt className="order-last text-xs text-ink-3">{k}</dt>
                </div>
              ))}
          </dl>
        </section>

        <section className="glass flex flex-col p-6">
          <div className="flex items-center justify-between pb-3 pl-3">
            <h2 className="font-display text-[15px] font-semibold tracking-[-0.01em]">Recent projects</h2>
            {!!data?.length && <Button variant="ghost" onClick={onAll}>All<ArrowRight size={13} /></Button>}
          </div>
          {first && <p className="px-3 py-6 text-[13px] text-ink-3">Projects you create appear here.</p>}
          {!!data?.length && <ProjectList projects={data} onSelect={onOpen} />}
        </section>
      </div>
    </div>
  )
}

/** The latest written lines, set on fanned 9:16 frames. Text preview of real output, not a render. */
function QuoteStack({ quotes }: { quotes: Recent[] }) {
  const slots = [0, 1, 2]
  return (
    <div aria-label={quotes.length ? 'Latest written quotes' : undefined} className="relative h-[250px] w-[230px] shrink-0 max-[1320px]:hidden">
      {slots.map((i) => {
        const q = quotes[i]
        return (
          <figure
            key={i}
            style={{ transform: `translateX(${(2 - i) * 38}px) rotate(${(i - 1) * 7}deg)`, zIndex: 3 - i }}
            className={cx(
              'absolute top-0 left-0 flex aspect-[9/16] w-[140px] items-end overflow-hidden rounded-[18px] p-3.5',
              'shadow-[0_18px_40px_-12px_rgb(10_5_2/0.7),inset_0_0_0_1px_rgb(255_244_232/0.1)]',
              i === 0 ? 'bg-[linear-gradient(160deg,#3a2a20,#1a1310_60%)]' : 'bg-[linear-gradient(160deg,#2b2320,#141110)]',
            )}
          >
            {q ? (
              <blockquote className={cx('font-display text-[12px] leading-snug font-semibold tracking-[-0.01em]', i > 0 && 'text-ink/70')}>{q.quote}</blockquote>
            ) : <span className="h-2 w-2/3 rounded-full bg-white/10" />}
          </figure>
        )
      })}
    </div>
  )
}
