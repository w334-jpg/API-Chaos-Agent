import { useState, useEffect } from "react"
import { GitBranch, Plus, Play, FileCode2, Trash2 } from "lucide-react"

interface Pipeline {
    id: string
    name: string
    config: {
        provider: string
        branch: string
        api_spec_path: string
        base_url: string
    }
    enabled: boolean
    last_run_status: string | null
}

interface PipelineRun {
    id: string
    status: string
    triggered_at: string
    commit_sha: string | null
    vulnerabilities_found: number
    max_severity: string | null
}

export default function CiCdPage() {
    const [pipelines, setPipelines] = useState<Pipeline[]>([])
    const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
    const [runs, setRuns] = useState<PipelineRun[]>([])
    const [configYaml, setConfigYaml] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchPipelines()
    }, [])

    async function fetchPipelines() {
        try {
            const res = await fetch("/api/v2/cicd/pipelines")
            if (res.ok) {
                const data = await res.json()
                setPipelines(data)
            }
        } catch {
            setPipelines([])
        } finally {
            setLoading(false)
        }
    }

    async function fetchRuns(pipelineId: string) {
        try {
            const res = await fetch(`/api/v2/cicd/pipelines/${pipelineId}/runs`)
            if (res.ok) setRuns(await res.json())
        } catch { setRuns([]) }
    }

    async function fetchConfig(pipelineId: string) {
        try {
            const res = await fetch(`/api/v2/cicd/pipelines/${pipelineId}/config`)
            if (res.ok) {
                const data = await res.json()
                setConfigYaml(data.config)
            }
        } catch { setConfigYaml(null) }
    }

    async function triggerPipeline(pipelineId: string) {
        try {
            await fetch(`/api/v2/cicd/pipelines/${pipelineId}/trigger`, { method: "POST" })
            fetchRuns(pipelineId)
        } catch { /* ignore */ }
    }

    async function deletePipeline(pipelineId: string) {
        try {
            await fetch(`/api/v2/cicd/pipelines/${pipelineId}`, { method: "DELETE" })
            fetchPipelines()
            if (selectedPipeline === pipelineId) {
                setSelectedPipeline(null)
                setRuns([])
                setConfigYaml(null)
            }
        } catch { /* ignore */ }
    }

    function selectPipeline(id: string) {
        setSelectedPipeline(id)
        fetchRuns(id)
        fetchConfig(id)
    }

    const providerLabels: Record<string, string> = {
        github_actions: "GitHub Actions",
        gitlab_ci: "GitLab CI",
        jenkins: "Jenkins",
        circleci: "CircleCI",
    }

    const runStatusColor: Record<string, string> = {
        completed: "text-green-600",
        running: "text-blue-600",
        failed: "text-red-600",
        pending: "text-yellow-600",
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">CI/CD Integration</h1>
                    <p className="text-muted-foreground">Configure and manage CI/CD pipeline integrations</p>
                </div>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="space-y-3">
                    <h2 className="font-semibold">Pipelines</h2>
                    {loading ? (
                        <p className="text-sm text-muted-foreground">Loading...</p>
                    ) : pipelines.length === 0 ? (
                        <div className="rounded-lg border border-dashed p-8 text-center">
                            <GitBranch className="mx-auto h-8 w-8 text-muted-foreground" />
                            <p className="mt-2 text-sm text-muted-foreground">No pipelines configured</p>
                        </div>
                    ) : (
                        pipelines.map((pipeline) => (
                            <div
                                key={pipeline.id}
                                onClick={() => selectPipeline(pipeline.id)}
                                className={`cursor-pointer rounded-lg border p-3 transition-colors ${selectedPipeline === pipeline.id ? "border-primary bg-primary/5" : "bg-card hover:border-primary/50"
                                    }`}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <GitBranch className="h-4 w-4" />
                                        <span className="font-medium">{pipeline.name}</span>
                                    </div>
                                    <div className="flex gap-1">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); triggerPipeline(pipeline.id) }}
                                            className="rounded p-1 hover:bg-accent"
                                            title="Trigger run"
                                        >
                                            <Play className="h-3.5 w-3.5" />
                                        </button>
                                        <button
                                            onClick={(e) => { e.stopPropagation(); deletePipeline(pipeline.id) }}
                                            className="rounded p-1 hover:bg-destructive/10 hover:text-destructive"
                                            title="Delete pipeline"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                    </div>
                                </div>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    {providerLabels[pipeline.config.provider] || pipeline.config.provider} · {pipeline.config.branch}
                                </p>
                            </div>
                        ))
                    )}
                </div>

                <div className="space-y-3 lg:col-span-2">
                    {selectedPipeline ? (
                        <>
                            <div>
                                <h2 className="font-semibold">Generated Config</h2>
                                {configYaml && (
                                    <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted p-4 text-xs">
                                        <code>{configYaml}</code>
                                    </pre>
                                )}
                            </div>
                            <div>
                                <h2 className="font-semibold">Pipeline Runs</h2>
                                {runs.length === 0 ? (
                                    <p className="mt-2 text-sm text-muted-foreground">No runs yet</p>
                                ) : (
                                    <div className="mt-2 space-y-2">
                                        {runs.map((run) => (
                                            <div key={run.id} className="flex items-center justify-between rounded-lg border bg-card p-3">
                                                <div>
                                                    <span className={`text-sm font-medium ${runStatusColor[run.status] || ""}`}>
                                                        {run.status}
                                                    </span>
                                                    {run.commit_sha && (
                                                        <span className="ml-2 text-xs text-muted-foreground">
                                                            {run.commit_sha.slice(0, 7)}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="text-right text-xs text-muted-foreground">
                                                    {run.vulnerabilities_found > 0 && (
                                                        <span className="text-red-600">{run.vulnerabilities_found} vulns</span>
                                                    )}
                                                    {run.max_severity && (
                                                        <span className="ml-2">Max: {run.max_severity}</span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <div className="flex h-48 items-center justify-center rounded-lg border border-dashed">
                            <p className="text-muted-foreground">Select a pipeline to view details</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
