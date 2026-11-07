import { useEffect, useRef, useState } from 'react'
import { Shell, type Page } from '../layouts/Shell'
import { Dashboard } from '../pages/Dashboard'
import { Create } from '../pages/Create'
import { Library } from '../pages/Library'
import { Projects } from '../pages/Projects'
import { Project } from '../pages/Project'
import { Queue } from '../pages/Queue'
import { Exports } from '../pages/Exports'
import { Settings } from '../pages/Settings'
import { Splash } from '../pages/Splash'

export function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [openProject, setOpenProject] = useState<string>()
  const [entered, setEntered] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const pending = useRef<ReturnType<typeof setTimeout>>(undefined)

  /** Navigate with a short exit: the old page lifts away into blur, then the new one plays its entrance. A second
   *  click mid-exit retargets instead of queueing; reduced motion switches at once. */
  function go(next: Page, project?: string) {
    const swap = () => {
      if (project) setOpenProject(project)
      setPage(next)
      setLeaving(false)
      document.querySelector('main')?.scrollTo({ top: 0 })
    }
    clearTimeout(pending.current)
    if (next === page && !project) { setLeaving(false); return }  // also cancels an exit already under way
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { swap(); return }
    setLeaving(true)
    pending.current = setTimeout(swap, 190)
  }
  useEffect(() => () => clearTimeout(pending.current), [])

  const open = (id: string) => go('project', id)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!entered) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); go('create') }
      if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); go('settings') }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })  // re-bound each render so the shortcuts always navigate from the current page

  if (!entered) return <Splash onCreate={() => setEntered(true)} />

  return (
    <Shell page={page} onNavigate={(p) => go(p)}>
      <div key={page === 'project' ? `project-${openProject}` : page} className={leaving ? 'anim-page-out' : 'anim-page'}>
        {page === 'dashboard' && <Dashboard onCreate={() => go('create')} onOpen={open} onAll={() => go('projects')} />}
        {page === 'create' && <Create onCreated={open} />}
        {page === 'projects' && <Projects onOpen={open} onCreate={() => go('create')} />}
        {page === 'library' && <Library onCreate={() => go('create')} />}
        {page === 'queue' && <Queue onOpen={open} />}
        {page === 'exports' && <Exports onOpenProject={open} />}
        {page === 'project' && openProject && (
          <Project id={openProject} onBack={() => go('projects')} onSettings={() => go('settings')} />
        )}
        {page === 'settings' && <Settings />}
      </div>
    </Shell>
  )
}
