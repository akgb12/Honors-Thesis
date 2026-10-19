import { Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import Dropzone from '../components/Dropzone'
import FileList from '../components/FileList'
import PreflightPanel from '../components/PreflightPanel'
import RunForm from '../components/RunForm'
import RunsList from '../components/RunsList'
import StepCard from '../components/StepCard'
import { Alert, Button, PageHeader, Skeleton } from '../components/ui'
import { errorMessage } from '../errors'
import { fileKind } from '../format'
import type { Effort, Preflight, Project, Run } from '../types'

export default function ProjectPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [preflight, setPreflight] = useState<Preflight | null>(null)
  const [checking, setChecking] = useState(false)
  const [mainFile, setMainFile] = useState<string | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [starting, setStarting] = useState(false)

  const runPreflight = useCallback(
    async (main: string | null) => {
      setChecking(true)
      try {
        setPreflight(await api.preflight(id, main))
        setError(null)
      } catch (e) {
        setPreflight(null)
        if (main) setMainFile(null)
        setError(errorMessage(e))
      } finally {
        setChecking(false)
      }
    },
    [id],
  )

  useEffect(() => {
    api
      .getProject(id)
      .then((value) => {
        setProject(value)
        if (value.files.length > 0) void runPreflight(null)
      })
      .catch((e) => setError(errorMessage(e)))
    api
      .listRuns(id)
      .then(setRuns)
      .catch((e) => setError(errorMessage(e)))
  }, [id, runPreflight])

  async function mutate(action: () => Promise<Project>, main: string | null = mainFile) {
    setBusy(true)
    try {
      setProject(await action())
      setError(null)
      await runPreflight(main)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  function selectMain(file: string) {
    setMainFile(file)
    void runPreflight(file)
  }

  async function startRun(effort: Effort, seedWeak: string | null) {
    setStarting(true)
    try {
      const run = await api.createRun(id, {
        effort,
        main_file: preflight?.main_file ?? mainFile,
        seed_weak: seedWeak,
      })
      navigate(`/runs/${run.id}`)
    } catch (e) {
      setError(errorMessage(e))
      setStarting(false)
    }
  }

  async function deleteProject() {
    if (!project || !window.confirm(`Delete “${project.name}” and all of its files and runs?`)) return
    try {
      await api.deleteProject(id)
      navigate('/')
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  if (!project) {
    return error ? (
      <Alert tone="danger" title="Could not load this project">
        {error}
      </Alert>
    ) : (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-56" />
      </div>
    )
  }

  const hasFiles = project.files.length > 0
  const onlyPdfs = hasFiles && project.files.every((file) => fileKind(file.path) === 'pdf')
  const ready = preflight?.ok === true
  let disabledReason: string | null = null
  if (!hasFiles) disabledReason = 'Upload your slides first.'
  else if (!ready) disabledReason = 'Resolve the pre-flight items above first.'

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: 'Projects', to: '/' }, { label: project.name }]}
        title={project.name}
        subtitle="Upload, check and run accessibility remediation on your Beamer slides."
        actions={
          <Button
            variant="danger"
            size="sm"
            onClick={deleteProject}
            icon={<Trash2 aria-hidden className="h-4 w-4" />}
          >
            Delete project
          </Button>
        }
      />

      {error && (
        <div className="mb-4">
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <StepCard
            number={1}
            title="Upload your slides"
            description="A .zip of the whole LaTeX project works best: .tex files, figures and style files."
            done={hasFiles && !onlyPdfs}
          >
            {onlyPdfs && (
              <div className="mb-4">
                <Alert tone="warning" title="Only PDF files were uploaded">
                  The pipeline needs the LaTeX source (.tex) of your Beamer slides. A PDF alone cannot
                  be remediated. Remove it and upload the source project as a .zip.
                </Alert>
              </div>
            )}
            <Dropzone
              compact={hasFiles}
              busy={busy}
              onFiles={(files) => void mutate(() => api.uploadFiles(id, files), null)}
            />
            {hasFiles && (
              <FileList
                files={project.files}
                disabled={busy}
                onRemove={(path) => void mutate(() => api.removeFile(id, path))}
              />
            )}
          </StepCard>

          <StepCard
            number={2}
            title="Check the project"
            description="We look for the main Beamer file and any missing images."
            done={ready}
          >
            {hasFiles ? (
              <PreflightPanel
                preflight={preflight}
                checking={checking}
                busy={busy}
                mainFile={mainFile}
                onSelectMain={selectMain}
                onFill={(path, file) => void mutate(() => api.putFile(id, path, file))}
              />
            ) : (
              <p className="text-sm text-slate-500">Upload files in step 1 to run the check.</p>
            )}
          </StepCard>

          <StepCard
            number={3}
            title="Run remediation"
            description="Adds figure descriptions and builds a tagged PDF. Uses the fake model unless the server is configured otherwise."
          >
            <RunForm
              disabled={!ready}
              disabledReason={disabledReason}
              loading={starting}
              onStart={(effort, seed) => void startRun(effort, seed)}
            />
          </StepCard>
        </div>

        <div className="lg:sticky lg:top-20">
          <RunsList runs={runs} />
        </div>
      </div>
    </div>
  )
}
