import { useEffect, useState } from 'react'
import { Shell, type Page } from '../layouts/Shell'
import { Dashboard } from '../pages/Dashboard'
import { Create } from '../pages/Create'
import { Projects } from '../pages/Projects'
import { Project } from '../pages/Project'
import { Settings } from '../pages/Settings'

export function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [openProject, setOpenProject] = useState<string>()

  const open = (id: string) => { setOpenProject(id); setPage('project') }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); setPage('create') }
      if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); setPage('settings') }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <Shell page={page} onNavigate={setPage}>
      <div key={page} className="anim-page">
        {page === 'dashboard' && <Dashboard onCreate={() => setPage('create')} onOpen={open} onAll={() => setPage('projects')} />}
        {page === 'create' && <Create onCreated={open} />}
        {page === 'projects' && <Projects onOpen={open} onCreate={() => setPage('create')} />}
        {page === 'project' && openProject && (
          <Project id={openProject} onBack={() => setPage('projects')} onSettings={() => setPage('settings')} />
        )}
        {page === 'settings' && <Settings />}
      </div>
    </Shell>
  )
}
