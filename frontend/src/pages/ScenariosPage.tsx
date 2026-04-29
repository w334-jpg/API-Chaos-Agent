import { useState } from "react"
import { api } from "@/services/api"
import type { Scenario, ScenarioType } from "@/types"
import ScenarioCard from "@/components/ScenarioCard"

const allTypes: ScenarioType[] = [
  "auth_bypass", "injection", "rate_limit", "data_leak",
  "error_handling", "input_validation", "ssl_tls", "cors",
  "dos", "business_logic",
]

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

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [schemaId, setSchemaId] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<ScenarioType | "all">("all")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const handleGenerate = async () => {
    if (!schemaId.trim()) return
    setIsLoading(true)
    setError(null)
    try {
      const result = await api.scenarios.generateBatch({ schema_id: schemaId })
      setScenarios(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed")
    } finally {
      setIsLoading(false)
    }
  }

  const toggleSelect = (scenario: Scenario) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(scenario.id)) {
        next.delete(scenario.id)
      } else {
        next.add(scenario.id)
      }
      return next
    })
  }

  const filtered = filterType === "all"
    ? scenarios
    : scenarios.filter((s) => s.type === filterType)

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Scenarios</h1>
        <p className="text-sm text-muted-foreground">
          Generate and manage chaos test scenarios
        </p>
      </div>

      {/* Generate Controls */}
      <div className="flex gap-3">
        <input
          type="text"
          value={schemaId}
          onChange={(e) => setSchemaId(e.target.value)}
          placeholder="Enter Schema ID"
          className="flex-1 rounded-lg border border-border bg-background px-4 py-2 text-sm placeholder:text-muted-foreground focus:border-chart-1 focus:outline-none"
        />
        <button
          onClick={handleGenerate}
          disabled={isLoading || !schemaId.trim()}
          className="rounded-lg bg-chart-1 px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-chart-1/90 disabled:opacity-50"
        >
          {isLoading ? "Generating..." : "Generate All"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Filter */}
      {scenarios.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setFilterType("all")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              filterType === "all"
                ? "bg-chart-1 text-background"
                : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
            }`}
          >
            All ({scenarios.length})
          </button>
          {allTypes.map((type) => {
            const count = scenarios.filter((s) => s.type === type).length
            if (count === 0) return null
            return (
              <button
                key={type}
                onClick={() => setFilterType(type)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  filterType === type
                    ? "bg-chart-1 text-background"
                    : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                }`}
              >
                {typeLabels[type]} ({count})
              </button>
            )
          })}
        </div>
      )}

      {/* Selected count */}
      {selectedIds.size > 0 && (
        <div className="rounded-lg bg-chart-1/10 p-3 text-sm">
          <span className="font-medium text-chart-1">{selectedIds.size}</span> scenarios selected
        </div>
      )}

      {/* Scenario Grid */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((scenario) => (
            <ScenarioCard
              key={scenario.id}
              scenario={scenario}
              selected={selectedIds.has(scenario.id)}
              onSelect={toggleSelect}
            />
          ))}
        </div>
      ) : scenarios.length > 0 ? (
        <div className="rounded-xl border border-border p-8 text-center text-sm text-muted-foreground">
          No scenarios match the selected filter.
        </div>
      ) : (
        <div className="rounded-xl border border-border p-8 text-center text-sm text-muted-foreground">
          No scenarios generated yet. Enter a Schema ID and click Generate.
        </div>
      )}
    </div>
  )
}
