// Exports (PRD §47): one row per export run, with the folder the user can open or copy.
import { Export } from '@phosphor-icons/react'
import { formatDate, studio, useQuery, type ExportRun } from '../lib/studio'
import { Button, ErrorNote, PageHeader } from '../components/ui'

export function Exports({ onOpenProject }: { onOpenProject: (id: string) => void }) {
  const { data, error, reload } = useQuery<ExportRun[]>('exports.list')

  async function open(run: ExportRun) {
    await studio.openExportPath(run.path)
    reload()
  }

  return (
    <>
      <PageHeader title="Exports">
        <Button variant="ghost" onClick={reload}>Refresh</Button>
      </PageHeader>
      {error && <div className="mb-6"><ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} /></div>}

      {data?.length === 0 && (
        <section className="grid max-w-md gap-3 py-12">
          <h2 className="text-base font-semibold">Nothing exported yet</h2>
          <p className="text-ink-2">Export copies every rendered piece into dated folders with captions, a cover frame
            and platform metadata, ready to upload or hand to Metricool.</p>
        </section>
      )}

      <ol className="glass px-8 py-2">
        {data?.map((run) => (
          <li key={run.id} className="grid grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-6 border-t border-line py-5 first:border-t-0">
            <span className="grid size-9 place-items-center rounded-2xl bg-accent/15 text-accent"><Export size={16} /></span>
            <span className="min-w-0">
              <button onClick={() => onOpenProject(run.project_id)} className="block truncate text-[14px] text-ink hover:underline">
                {run.project}
              </button>
              <span className="block truncate text-xs text-ink-3">{run.path}</span>
            </span>
            <span className="flex shrink-0 items-center gap-2 text-xs text-ink-3">
              {formatDate(run.created_at)} · {run.pieces} {run.pieces === 1 ? 'piece' : 'pieces'}
              <Button variant="ghost" onClick={() => studio.openExportPath(run.path)}>Open folder</Button>
              <Button variant="ghost" onClick={() => navigator.clipboard.writeText(run.path)}>Copy path</Button>
            </span>
          </li>
        ))}
      </ol>
    </>
  )
}
