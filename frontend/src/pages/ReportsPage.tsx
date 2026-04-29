import { useState } from "react"
import { api } from "@/services/api"
import type { Report } from "@/types"
import ReportView from "@/components/ReportView"

export default function ReportsPage() {
  const [reportId, setReportId] = useState("")
  const [executionId, setExecutionId] = useState("")
  const [report, setReport] = useState<Report | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    if (!executionId.trim()) return
    setIsLoading(true)
    setError(null)
    try {
      const result = await api.reports.generate({ execution_id: executionId })
      setReport(result)
      setReportId(result.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report generation failed")
    } finally {
      setIsLoading(false)
    }
  }

  const handleFetch = async () => {
    if (!reportId.trim()) return
    setIsLoading(true)
    setError(null)
    try {
      const result = await api.reports.get(reportId)
      setReport(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch report")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">
          View test reports with severity breakdown
        </p>
      </div>

      {/* Controls */}
      <div className="rounded-xl border border-border p-6 space-y-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={executionId}
            onChange={(e) => setExecutionId(e.target.value)}
            placeholder="Execution ID (to generate report)"
            className="flex-1 rounded-lg border border-border bg-background px-4 py-2 text-sm placeholder:text-muted-foreground focus:border-chart-1 focus:outline-none"
          />
          <button
            onClick={handleGenerate}
            disabled={isLoading || !executionId.trim()}
            className="rounded-lg bg-chart-1 px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-chart-1/90 disabled:opacity-50"
          >
            {isLoading ? "Generating..." : "Generate Report"}
          </button>
        </div>

        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>or</span>
        </div>

        <div className="flex gap-3">
          <input
            type="text"
            value={reportId}
            onChange={(e) => setReportId(e.target.value)}
            placeholder="Report ID (to fetch existing)"
            className="flex-1 rounded-lg border border-border bg-background px-4 py-2 text-sm placeholder:text-muted-foreground focus:border-chart-1 focus:outline-none"
          />
          <button
            onClick={handleFetch}
            disabled={isLoading || !reportId.trim()}
            className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary/80 disabled:opacity-50"
          >
            Fetch Report
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Report View */}
      {report && <ReportView report={report} />}
    </div>
  )
}
