import { useState } from 'react'
import { Plus } from '@phosphor-icons/react'
import { call, formatDate, useQuery, BackendError, type Project } from '../lib/studio'
import { Button, ErrorNote, PageHeader } from '../components/ui'
import { ProjectList } from '../components/ProjectList'

export function Projects({ onOpen, onCreate }: { onOpen: (id: string) => void; onCreate: () => void }) {
  const { data, error, reload } = useQuery<Project[]>('projects.list')
  const [deleteError, setDeleteError] = useState<BackendError>()

  async function remove(p: Project) {
    if (!confirm(`Delete "${p.name}" (${formatDate(p.created_at)}) and everything generated for it? This can't be undone.`)) return
    try {
      await call('projects.delete', { id: p.id })
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
      {(error || deleteError) && <div className="mb-6"><ErrorNote error={(error || deleteError)!} action={error && <Button onClick={reload}>Try again</Button>} /></div>}
      {data?.length === 0 && (
        <section className="grid max-w-md gap-3 py-16">
          <h2 className="text-base font-semibold">No projects yet</h2>
          <p className="text-ink-2">A project holds one creative brief and every piece generated from it.</p>
          <div className="pt-2"><Button variant="primary" onClick={onCreate}>Create content</Button></div>
        </section>
      )}
      {!!data?.length && (
        <section className="glass p-4">
          <ProjectList projects={data} onSelect={onOpen}
            onDelete={(id) => { const p = data.find((x) => x.id === id); if (p) remove(p) }} />
        </section>
      )}
    </>
  )
}
