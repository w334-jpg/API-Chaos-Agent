import { useState } from "react"
import type { Report, ReportFinding } from "@/types"
import SeverityBadge from "./SeverityBadge"
import { ChevronDown, ChevronRight, ShieldAlert } from "lucide-react"

function FindingRow({ finding }: { finding: ReportFinding }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/30"
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{finding.title}</span>
            <SeverityBadge severity={finding.severity} />
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {finding.method} {finding.endpoint}
          </p>
        </div>
      </button>
      {expanded && (
        <div className="space-y-3 border-t border-border bg-muted/20 px-4 py-3 pl-11">
          <p className="text-sm text-muted-foreground">{finding.description}</p>
          {finding.details && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Details</p>
              <pre className="overflow-x-auto rounded-lg bg-background p-3 text-xs">{finding.details}</pre>
            </div>
          )}
          {finding.recommendation && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Recommendation</p>
              <p className="text-sm">{finding.recommendation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface ReportViewProps {
  report: Report
}

export default function ReportView({ report }: ReportViewProps) {
  const severityOrder: Array<keyof typeof report.summary.severity_breakdown> = [
    "critical", "high", "medium", "low", "info",
  ]

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="rounded-xl border border-border p-6">
        <h3 className="mb-4 text-sm font-medium">Summary</h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-lg bg-emerald-500/10 p-4 text-center">
            <p className="text-2xl font-bold text-emerald-400">{report.summary.passed}</p>
            <p className="text-xs text-muted-foreground">Passed</p>
          </div>
          <div className="rounded-lg bg-red-500/10 p-4 text-center">
            <p className="text-2xl font-bold text-red-400">{report.summary.failed}</p>
            <p className="text-xs text-muted-foreground">Failed</p>
          </div>
          <div className="rounded-lg bg-muted p-4 text-center">
            <p className="text-2xl font-bold">{report.summary.total_scenarios}</p>
            <p className="text-xs text-muted-foreground">Total</p>
          </div>
        </div>

        {/* Severity Breakdown */}
        <div className="mt-4 flex flex-wrap gap-2">
          {severityOrder.map((sev) => {
            const count = report.summary.severity_breakdown[sev]
            if (!count) return null
            return (
              <div key={sev} className="flex items-center gap-1.5">
                <SeverityBadge severity={sev} />
                <span className="text-xs text-muted-foreground">x{count}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Findings */}
      <div className="rounded-xl border border-border">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <ShieldAlert className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">
            Findings ({report.findings.length})
          </h3>
        </div>
        {report.findings.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No findings. All scenarios passed.
          </div>
        ) : (
          <div>
            {report.findings.map((f) => (
              <FindingRow key={f.id} finding={f} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
