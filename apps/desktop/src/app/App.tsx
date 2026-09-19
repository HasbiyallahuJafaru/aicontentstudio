import { useEffect, useState } from 'react'
import { Shell, type Page } from '../layouts/Shell'
import { Dashboard } from '../pages/Dashboard'
import { Create } from '../pages/Create'
import { Projects } from '../pages/Projects'
import { Settings } from '../pages/Settings'

export function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [openProject, setOpenProject] = useState<string>()

  const open = (id: string) => { setOpenProject(id); setPage('projects') }

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
        {page === 'dashboard' && <Dashboard onCreate={() => setPage('create')} onOpen={open} />}
        {page === 'create' && <Create onCreated={open} />}
        {page === 'projects' && <Projects selected={openProject} onSelect={setOpenProject} onCreate={() => setPage('create')} />}
        {page === 'settings' && <Settings />}
      </div>
    </Shell>
  )
}
