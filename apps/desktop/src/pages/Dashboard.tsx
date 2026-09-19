import { Plus } from '@phosphor-icons/react'
import { useQuery, type Project } from '../lib/studio'
import { Button, ErrorNote, PageHeader } from '../components/ui'
import { ProjectList } from '../components/ProjectList'

export function Dashboard({ onCreate, onOpen }: { onCreate: () => void; onOpen: (id: string) => void }) {
  const { data, error, reload } = useQuery<Project[]>('projects.list', { limit: 8 })

  return (
    <>
      <PageHeader title="Dashboard">
        <Button variant="primary" onClick={onCreate} kbd="Ctrl N"><Plus size={14} weight="bold" />New project</Button>
      </PageHeader>

      {error && <ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} />}

      {data?.length === 0 && (
        <section className="grid max-w-md gap-3 py-16">
          <h2 className="text-base font-semibold">No projects yet</h2>
          <p className="text-ink-2">
            Create your first content batch and we'll build the visuals, narration and final renders for you.
          </p>
          <div className="pt-2"><Button variant="primary" onClick={onCreate}>Create content</Button></div>
        </section>
      )}

      {!!data?.length && (
        <section className="grid gap-3">
          <h2 className="px-3 text-[13px] font-medium text-ink-2">Recent projects</h2>
          <ProjectList projects={data} onSelect={onOpen} />
        </section>
      )}
    </>
  )
}
