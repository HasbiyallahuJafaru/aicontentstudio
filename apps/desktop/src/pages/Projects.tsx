import { useState } from 'react'
import { Plus, Trash } from '@phosphor-icons/react'
import { call, FORMATS, formatDate, label, PLATFORMS, useQuery, BackendError, type Project } from '../lib/studio'
import { Button, ErrorNote, PageHeader } from '../components/ui'
import { ProjectList } from '../components/ProjectList'

export function Projects({ selected, onSelect, onCreate }: { selected?: string; onSelect: (id?: string) => void; onCreate: () => void }) {
  const { data, error, reload } = useQuery<Project[]>('projects.list')
  const [deleteError, setDeleteError] = useState<BackendError>()
  const current = data?.find((p) => p.id === selected)

  async function remove(p: Project) {
    if (!confirm(`Delete "${p.name}" (${formatDate(p.created_at)})? This can't be undone.`)) return
    try {
      await call('projects.delete', { id: p.id })
      onSelect(undefined)
      reload()
    } catch (e) {
      setDeleteError(e as BackendError)
    }
  }

  return (
    <>
      <PageHeader title="Projects">
        <Button variant="primary" onClick={onCreate} kbd="Ctrl N"><Plus size={14} weight="bold" />New project</Button>
      </PageHeader>
      {error && <ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} />}
      {data?.length === 0 && (
        <section className="grid max-w-md gap-3 py-16">
          <h2 className="text-base font-semibold">No projects yet</h2>
          <p className="text-ink-2">A project holds one creative brief and every piece generated from it.</p>
          <div className="pt-2"><Button variant="primary" onClick={onCreate}>Create content</Button></div>
        </section>
      )}
      {!!data?.length && (
        <div className="grid grid-cols-[minmax(0,1fr)_360px] gap-8">
          <ProjectList projects={data} selected={selected} onSelect={onSelect}
            onDelete={(id) => { const p = data.find((x) => x.id === id); if (p) remove(p) }} />
          {current ? <Detail project={current} onDelete={() => remove(current)} error={deleteError} />
            : <p className="pt-3 text-[13px] text-ink-3">Select a project to see its brief.</p>}
        </div>
      )}
    </>
  )
}

function Detail({ project: p, onDelete, error }: { project: Project; onDelete: () => void; error?: BackendError }) {
  const rows: [string, string][] = [
    ['Status', label(p.status)],
    ['Tone', label(p.brief.tone)],
    ['Output', FORMATS.find((f) => f.value === p.brief.format)!.label],
    ['Pieces', String(p.brief.quantity)],
    ['Platforms', p.brief.platforms.map((x) => PLATFORMS.find((y) => y.value === x)!.label).join(', ')],
    ...(p.brief.mood ? [['Mood', p.brief.mood] as [string, string]] : []),
    ...(p.brief.audience ? [['Audience', p.brief.audience] as [string, string]] : []),
    ['Created', formatDate(p.created_at)],
  ]
  return (
    <aside className="sticky top-0 grid content-start gap-5 self-start rounded-panel bg-panel p-6" aria-label="Project details">
      <h2 className="font-display text-lg font-semibold tracking-[-0.01em]">{p.name}</h2>
      <dl className="grid grid-cols-[88px_1fr] gap-x-4 gap-y-2.5 text-[13px]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-3">{k}</dt>
            <dd data-selectable className="text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {error && <ErrorNote error={error} />}
      <div className="border-t border-line pt-4">
        <Button variant="danger" onClick={onDelete} className="-ml-3"><Trash size={14} />Delete project</Button>
      </div>
    </aside>
  )
}
