import type { Scenario, ScenarioType } from "@/types"
import SeverityBadge from "./SeverityBadge"
import { FlaskConical } from "lucide-react"

const typeLabels: Record<ScenarioType, string> = {
  auth_bypass: "Auth Bypass",
  injection: "Injection",
  rate_limit: "Rate Limit",
  data_leak: "Data Leak",
  error_handling: "Error Handling",
  input_validation: "Input Validation",
  ssl_tls: "SSL/TLS",
  cors: "CORS",
  dos: "DoS",
  business_logic: "Business Logic",
}

const typeColors: Record<ScenarioType, string> = {
  auth_bypass: "bg-red-500/15 text-red-400",
  injection: "bg-purple-500/15 text-purple-400",
  rate_limit: "bg-amber-500/15 text-amber-400",
  data_leak: "bg-pink-500/15 text-pink-400",
  error_handling: "bg-orange-500/15 text-orange-400",
  input_validation: "bg-blue-500/15 text-blue-400",
  ssl_tls: "bg-cyan-500/15 text-cyan-400",
  cors: "bg-teal-500/15 text-teal-400",
  dos: "bg-rose-500/15 text-rose-400",
  business_logic: "bg-indigo-500/15 text-indigo-400",
}

interface ScenarioCardProps {
  scenario: Scenario
  selected?: boolean
  onSelect?: (scenario: Scenario) => void
}

export default function ScenarioCard({ scenario, selected, onSelect }: ScenarioCardProps) {
  return (
    <div
      onClick={() => onSelect?.(scenario)}
      className={`rounded-xl border p-4 transition-colors ${
        selected
          ? "border-chart-1 bg-chart-1/5"
          : "border-border hover:border-muted-foreground/30"
      } ${onSelect ? "cursor-pointer" : ""}`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">{scenario.name}</h3>
        </div>
        <SeverityBadge severity={scenario.severity} />
      </div>
      <p className="mb-3 text-xs text-muted-foreground line-clamp-2">{scenario.description}</p>
      <div className="flex items-center gap-2">
        <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${typeColors[scenario.type]}`}>
          {typeLabels[scenario.type]}
        </span>
        <span className="text-xs text-muted-foreground">
          {scenario.method} {scenario.endpoint}
        </span>
      </div>
    </div>
  )
}
