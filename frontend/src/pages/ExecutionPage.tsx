import { useState, useEffect, useCallback } from "react"
import { api } from "@/services/api"
import type { Execution } from "@/types"
import ExecutionProgress from "@/components/ExecutionProgress"

export default function ExecutionPage() {
  const [scenarioIds, setScenarioIds] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [execution, setExecution] = useState<Execution | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pollStatus = useCallback(async (executionId: string) => {
    try {
      const status = await api.execution.getStatus(executionId)
      setExecution(status)
      if (status.status === "running" || status.status === "pending") {
        setTimeout(() => pollStatus(executionId), 2000)
      }
    } catch {
      // Stop polling on error
    }
  }, [])

  const handleRun = async () => {
    const ids = scenarioIds
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
    if (ids.length === 0) return

    setIsLoading(true)
    setError(null)
    try {
      const result = await api.execution.run({
        scenario_ids: ids,
        base_url: baseUrl || undefined,
      })
      setExecution(result)
      pollStatus(result.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed")
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    return () => {
      // Cleanup polling on unmount
    }
  }, [])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Execution</h1>
        <p className="text-sm text-muted-foreground">
          Configure and run chaos test executions
        </p>
      </div>

      {/* Configuration */}
      <div className="rounded-xl border border-border p-6 space-y-4">
        <h2 className="text-lg font-semibold">Configuration</h2>

        <div>
          <label className="mb-1.5 block text-sm font-medium">Scenario IDs</label>
          <textarea
            value={scenarioIds}
            onChange={(e) => setScenarioIds(e.target.value)}
            placeholder="Enter scenario IDs, comma-separated"
            rows={3}
            className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm placeholder:text-muted-foreground focus:border-chart-1 focus:outline-none"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">Base URL (optional)</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.example.com"
            className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm placeholder:text-muted-foreground focus:border-chart-1 focus:outline-none"
          />
        </div>

        <button
          onClick={handleRun}
          disabled={isLoading || !scenarioIds.trim()}
          className="rounded-lg bg-chart-1 px-6 py-2.5 text-sm font-medium text-background transition-colors hover:bg-chart-1/90 disabled:opacity-50"
        >
          {isLoading ? "Starting..." : "Run Execution"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Execution Progress */}
      {execution && (
        <div className="space-y-4">
          <ExecutionProgress
            status={execution.status}
            progress={execution.progress}
            total={execution.total}
          />

          {/* Execution Details */}
          <div className="rounded-xl border border-border p-6">
            <h3 className="mb-3 text-sm font-medium">Execution Details</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Execution ID</p>
                <p className="font-mono text-xs">{execution.id}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Started</p>
                <p>{new Date(execution.started_at).toLocaleString()}</p>
              </div>
            </div>
          </div>

          {/* Results */}
          {execution.results && execution.results.length > 0 && (
            <div className="rounded-xl border border-border">
              <div className="border-b border-border px-4 py-3">
                <h3 className="text-sm font-medium">
                  Results ({execution.results.length})
                </h3>
              </div>
              <div className="divide-y divide-border">
                {execution.results.map((result, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        result.passed ? "bg-emerald-400" : "bg-red-400"
                      }`}
                    />
                    <span className="flex-1 text-sm font-mono text-xs">
                      {result.scenario_id}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {result.passed ? "Passed" : result.finding || "Failed"}
                    </span>
                    {result.duration_ms != null && (
                      <span className="text-xs text-muted-foreground">
                        {result.duration_ms}ms
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
