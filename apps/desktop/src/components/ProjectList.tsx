import { FORMATS, formatDate, label, type Project } from '../lib/studio'
import { cx } from './ui'

const formatLabel = (f: string) => FORMATS.find((x) => x.value === f)?.label ?? f

export function ProjectList({ projects, selected, onSelect, onDelete }: {
  projects: Project[]
  selected?: string
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
}) {
  return (
    <ul className="grid gap-px" aria-label="Projects">
      {projects.map((p) => (
        <li key={p.id}>
          <button
            onClick={() => onSelect(p.id)}
            onKeyDown={(e) => e.key === 'Delete' && onDelete?.(p.id)}
            aria-current={selected === p.id || undefined}
            className={cx(
              'grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-6 rounded-control px-3 py-2.5 text-left transition-colors duration-150',
              selected === p.id ? 'bg-raised' : 'hover:bg-raised/60',
            )}
          >
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium text-ink">{p.name}</span>
              <span className="block truncate text-xs text-ink-3">
                {label(p.brief.tone)}, {formatLabel(p.brief.format).toLowerCase()}, {p.brief.quantity} {p.brief.quantity === 1 ? 'piece' : 'pieces'}
              </span>
            </span>
            <span className="tnum text-xs text-ink-3">{formatDate(p.created_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
