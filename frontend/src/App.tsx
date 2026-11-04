import { Accessibility } from 'lucide-react'
import { Link, Route, Routes } from 'react-router-dom'
import { Badge } from './components/ui'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'
import RunPage from './pages/RunPage'

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-screen-2xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-3 rounded-lg">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-800 text-white shadow-sm">
              <Accessibility aria-hidden className="h-5 w-5" />
            </span>
            <span className="text-base font-semibold tracking-tight text-slate-900">
              Accessible Slides
            </span>
            <Badge tone="brand">Mark 1</Badge>
          </Link>
          <nav aria-label="Main">
            <Link
              to="/"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Projects
            </Link>
          </nav>
        </div>
      </header>
      <main id="content" className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-8 sm:px-6">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-400">
        Preliminary accessibility (A) and fidelity (F) scores. Mark 1 research prototype.
      </footer>
    </div>
  )
}
