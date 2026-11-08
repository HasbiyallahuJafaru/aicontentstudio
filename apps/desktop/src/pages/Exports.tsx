// Exports (PRD §47): one row per export run, with the folder the user can open or copy.
import { useState, type CSSProperties } from 'react'
import { Check, Export, FolderOpen, Trash } from '@phosphor-icons/react'
import { BackendError, call, formatDate, studio, useQuery, type ExportRun } from '../lib/studio'
import { Button, ErrorNote, PageHeader, spot } from '../components/ui'
import { Cover } from '../components/Cover'

export function Exports({ onOpenProject }: { onOpenProject: (id: string) => void }) {
  const { data, error, reload } = useQuery<ExportRun[]>('exports.list')
  const [deleteError, setDeleteError] = useState<BackendError>()

  async function remove(run: ExportRun) {
    if (!confirm(`Delete the "${run.project}" export? Its folders are removed from disk; the project and its renders stay.`)) return
    setDeleteError(undefined)
    try { await call('exports.delete', { export_id: run.id }); reload() } catch (e) { setDeleteError(e as BackendError) }
  }

  return (
    <>
      <PageHeader title="Exports">
        <Button variant="ghost" onClick={reload}>Refresh</Button>
      </PageHeader>
      {error && <div className="mb-6"><ErrorNote error={error} action={<Button onClick={reload}>Try again</Button>} /></div>}
      {deleteError && <div className="mb-6"><ErrorNote error={deleteError} /></div>}

      {data?.length === 0 && (
        <section className="grid max-w-md gap-3 py-12">
          <h2 className="text-base font-semibold">Nothing exported yet</h2>
          <p className="text-ink-2">Export copies every rendered piece into dated folders with captions, a cover frame
            and platform metadata, ready to upload or hand to Metricool.</p>
        </section>
      )}

      <ol className="grid gap-4">
        {data?.map((run, i) => (
          <li key={run.id} onMouseMove={spot} className="glass spotlight anim-slot grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-8 px-7 py-6 max-[900px]:grid-cols-[auto_minmax(0,1fr)]"
            style={{ '--i': Math.min(i, 10) } as CSSProperties}>
            <Proofs covers={run.covers} />
            <div className="grid min-w-0 gap-1.5">
              <button onClick={() => onOpenProject(run.project_id)}
                className="w-fit max-w-full truncate text-left font-display text-[18px] font-semibold tracking-[-0.015em] text-ink transition-colors duration-200 hover:text-accent-ink">
                {run.project}
              </button>
              <span className="text-[13px] text-ink-2">{run.pieces} {run.pieces === 1 ? 'piece' : 'pieces'} · {formatDate(run.created_at)}</span>
              <span title={run.path} className="truncate font-mono text-2xs text-ink-3">{run.path}</span>
            </div>
            <span className="flex shrink-0 items-center gap-1 max-[900px]:col-span-2">
              <Button onClick={() => studio.openExportPath(run.path)}><FolderOpen size={14} />Open folder</Button>
              <CopyPath path={run.path} />
              <Button variant="ghost" className="!px-2" aria-label={`Delete the ${run.project} export`} title="Delete this export's folders"
                onClick={() => remove(run)}><Trash size={14} /></Button>
            </span>
          </li>
        ))}
      </ol>
    </>
  )
}

/** The export's real output as a small stack of proofs, fanned like prints on a desk. */
function Proofs({ covers }: { covers: string[] }) {
  if (!covers.length) return <span className="grid size-16 place-items-center rounded-2xl bg-accent/15 text-accent-ink"><Export size={20} /></span>
  return (
    <div aria-hidden className="relative h-[84px]" style={{ width: 56 + (covers.length - 1) * 22 }}>
      {covers.map((c, i) => (
        <div key={c} className="absolute top-0 w-[56px]"
          style={{ left: i * 22, zIndex: covers.length - i, transform: `rotate(${(i - (covers.length - 1) / 2) * 6}deg)` }}>
          <Cover src={c} size="sm" className="!rounded-[10px]" />
        </div>
      ))}
    </div>
  )
}

function CopyPath({ path }: { path: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(path)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }
  return (
    <Button variant="ghost" onClick={copy} aria-live="polite">
      {copied ? <><Check size={13} weight="bold" className="text-ok" />Copied</> : 'Copy path'}
    </Button>
  )
}
