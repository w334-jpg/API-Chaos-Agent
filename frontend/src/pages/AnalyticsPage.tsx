import { useState } from "react"
import { BarChart3, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2 } from "lucide-react"

interface AnalyticsSummary {
    total_executions: number
    total_scenarios_run: number
    total_vulnerabilities: number
    severity_distribution: Record<string, number>
    pass_rate: number
    avg_execution_time_ms: number
    top_risk_endpoints: Array<{
        endpoint_path: string
        endpoint_method: string
        risk_score: number
        total_findings: number
        critical_count: number
    }>
    trends: Array<{
        date: string
        critical: number
        high: number
        medium: number
        low: number
        total: number
    }>
}

interface ComparisonResult {
    new_findings: number
    resolved_findings: number
    persistent_findings: number
    risk_score_delta: number
    improved: boolean
}

export default function AnalyticsPage() {
    const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
    const [comparison, setComparison] = useState<ComparisonResult | null>(null)
    const [baselineId, setBaselineId] = useState("")
    const [comparisonId, setComparisonId] = useState("")
    const [loading, setLoading] = useState(false)

    async function fetchSummary() {
        setLoading(true)
        try {
            const res = await fetch("/api/v2/analytics/summary/default")
            if (res.ok) setSummary(await res.json())
        } catch { setSummary(null) }
        finally { setLoading(false) }
    }

    async function compareReports() {
        if (!baselineId || !comparisonId) return
        try {
            const res = await fetch(`/api/v2/analytics/compare?baseline_report_id=${baselineId}&comparison_report_id=${comparisonId}`)
            if (res.ok) setComparison(await res.json())
        } catch { setComparison(null) }
    }

    const severityColors: Record<string, string> = {
        critical: "bg-red-500",
        high: "bg-orange-500",
        medium: "bg-yellow-500",
        low: "bg-blue-500",
        info: "bg-gray-400",
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">Analytics</h1>
                    <p className="text-muted-foreground">Advanced analytics, trends, and report comparison</p>
                </div>
                <button
                    onClick={fetchSummary}
                    className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                    Refresh
                </button>
            </div>

            {loading && <p className="text-muted-foreground">Loading analytics...</p>}

            {summary && (
                <>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                        <div className="rounded-lg border bg-card p-4">
                            <p className="text-sm text-muted-foreground">Total Executions</p>
                            <p className="mt-1 text-2xl font-bold">{summary.total_executions}</p>
                        </div>
                        <div className="rounded-lg border bg-card p-4">
                            <p className="text-sm text-muted-foreground">Pass Rate</p>
                            <p className="mt-1 text-2xl font-bold">{summary.pass_rate}%</p>
                        </div>
                        <div className="rounded-lg border bg-card p-4">
                            <p className="text-sm text-muted-foreground">Vulnerabilities</p>
                            <p className="mt-1 text-2xl font-bold">{summary.total_vulnerabilities}</p>
                        </div>
                        <div className="rounded-lg border bg-card p-4">
                            <p className="text-sm text-muted-foreground">Avg Execution Time</p>
                            <p className="mt-1 text-2xl font-bold">{summary.avg_execution_time_ms.toFixed(0)}ms</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                        <div className="rounded-lg border bg-card p-5">
                            <h2 className="mb-4 font-semibold">Severity Distribution</h2>
                            <div className="space-y-3">
                                {Object.entries(summary.severity_distribution).map(([severity, count]) => (
                                    <div key={severity} className="flex items-center gap-3">
                                        <div className={`h-3 w-3 rounded-full ${severityColors[severity] || "bg-gray-400"}`} />
                                        <span className="w-20 text-sm capitalize">{severity}</span>
                                        <div className="flex-1">
                                            <div className="h-2 rounded-full bg-muted">
                                                <div
                                                    className={`h-2 rounded-full ${severityColors[severity] || "bg-gray-400"}`}
                                                    style={{ width: `${Math.min((count / Math.max(summary.total_vulnerabilities, 1)) * 100, 100)}%` }}
                                                />
                                            </div>
                                        </div>
                                        <span className="text-sm font-medium">{count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="rounded-lg border bg-card p-5">
                            <h2 className="mb-4 font-semibold">Top Risk Endpoints</h2>
                            {summary.top_risk_endpoints.length === 0 ? (
                                <p className="text-sm text-muted-foreground">No risk data available</p>
                            ) : (
                                <div className="space-y-2">
                                    {summary.top_risk_endpoints.slice(0, 5).map((ep, i) => (
                                        <div key={i} className="flex items-center justify-between rounded-lg border p-2">
                                            <div>
                                                <span className="text-xs font-medium text-muted-foreground">{ep.endpoint_method}</span>
                                                <p className="text-sm font-medium">{ep.endpoint_path}</p>
                                            </div>
                                            <div className="text-right">
                                                <span className="text-lg font-bold text-red-600">{ep.risk_score.toFixed(0)}</span>
                                                <p className="text-xs text-muted-foreground">risk score</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {summary.trends.length > 0 && (
                        <div className="rounded-lg border bg-card p-5">
                            <h2 className="mb-4 font-semibold">Severity Trends</h2>
                            <div className="space-y-2">
                                {summary.trends.map((trend) => (
                                    <div key={trend.date} className="flex items-center gap-4 rounded-lg border p-2">
                                        <span className="w-24 text-sm text-muted-foreground">{trend.date}</span>
                                        <div className="flex gap-3 text-sm">
                                            {trend.critical > 0 && <span className="text-red-600">{trend.critical} critical</span>}
                                            {trend.high > 0 && <span className="text-orange-600">{trend.high} high</span>}
                                            {trend.medium > 0 && <span className="text-yellow-600">{trend.medium} medium</span>}
                                            {trend.low > 0 && <span className="text-blue-600">{trend.low} low</span>}
                                        </div>
                                        <span className="ml-auto text-sm font-medium">{trend.total} total</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}

            <div className="rounded-lg border bg-card p-5">
                <h2 className="mb-4 font-semibold">Report Comparison</h2>
                <div className="flex items-end gap-3">
                    <div className="flex-1">
                        <label className="text-sm font-medium">Baseline Report ID</label>
                        <input
                            type="text"
                            value={baselineId}
                            onChange={(e) => setBaselineId(e.target.value)}
                            placeholder="report-id-1"
                            className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                        />
                    </div>
                    <div className="flex-1">
                        <label className="text-sm font-medium">Comparison Report ID</label>
                        <input
                            type="text"
                            value={comparisonId}
                            onChange={(e) => setComparisonId(e.target.value)}
                            placeholder="report-id-2"
                            className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                        />
                    </div>
                    <button
                        onClick={compareReports}
                        disabled={!baselineId || !comparisonId}
                        className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                        Compare
                    </button>
                </div>

                {comparison && (
                    <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
                        <div className="rounded-lg border p-3">
                            <div className="flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-red-500" />
                                <span className="text-sm font-medium">New</span>
                            </div>
                            <p className="mt-1 text-xl font-bold text-red-600">{comparison.new_findings}</p>
                        </div>
                        <div className="rounded-lg border p-3">
                            <div className="flex items-center gap-2">
                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                <span className="text-sm font-medium">Resolved</span>
                            </div>
                            <p className="mt-1 text-xl font-bold text-green-600">{comparison.resolved_findings}</p>
                        </div>
                        <div className="rounded-lg border p-3">
                            <div className="flex items-center gap-2">
                                <BarChart3 className="h-4 w-4 text-yellow-500" />
                                <span className="text-sm font-medium">Persistent</span>
                            </div>
                            <p className="mt-1 text-xl font-bold">{comparison.persistent_findings}</p>
                        </div>
                        <div className="rounded-lg border p-3">
                            <div className="flex items-center gap-2">
                                {comparison.improved ? (
                                    <TrendingDown className="h-4 w-4 text-green-500" />
                                ) : (
                                    <TrendingUp className="h-4 w-4 text-red-500" />
                                )}
                                <span className="text-sm font-medium">Risk Score</span>
                            </div>
                            <p className={`mt-1 text-xl font-bold ${comparison.improved ? "text-green-600" : "text-red-600"}`}>
                                {comparison.risk_score_delta > 0 ? "+" : ""}{comparison.risk_score_delta.toFixed(1)}
                            </p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
