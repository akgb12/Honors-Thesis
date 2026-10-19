import { Link, Route, Routes } from 'react-router-dom'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'
import RunPage from './pages/RunPage'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white px-4 py-3">
        <Link to="/" className="text-lg font-semibold">
          Accessible slides (Mark 1)
        </Link>
      </header>
      <main className="mx-auto max-w-screen-2xl p-4">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}
