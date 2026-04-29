import type {
  UploadResponse,
  ParseResponse,
  ApiEndpoint,
  Scenario,
  Execution,
  Report,
  HealthStatus,
  GenerateScenariosRequest,
  GenerateBatchRequest,
  RunExecutionRequest,
  GenerateReportRequest,
} from "@/types"

const API_BASE = "/api"

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export const api = {
  health: {
    check: () => request<HealthStatus>("/health"),
  },

  schema: {
    upload: async (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      const response = await fetch(`${API_BASE}/schema/upload`, {
        method: "POST",
        body: formData,
      })
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }
      return response.json() as Promise<UploadResponse>
    },

    parse: (schemaId: string) =>
      request<ParseResponse>("/schema/parse", {
        method: "POST",
        body: JSON.stringify({ schema_id: schemaId }),
      }),

    getEndpoints: (schemaId: string) =>
      request<ApiEndpoint[]>(`/schema/${schemaId}/endpoints`),
  },

  scenarios: {
    generate: (data: GenerateScenariosRequest) =>
      request<Scenario[]>("/scenarios/generate", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    generateBatch: (data: GenerateBatchRequest) =>
      request<Scenario[]>("/scenarios/generate-batch", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    get: (scenarioId: string) =>
      request<Scenario>(`/scenarios/${scenarioId}`),
  },

  execution: {
    run: (data: RunExecutionRequest) =>
      request<Execution>("/execution/run", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    getStatus: (executionId: string) =>
      request<Execution>(`/execution/${executionId}/status`),
  },

  reports: {
    generate: (data: GenerateReportRequest) =>
      request<Report>("/reports/generate", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    get: (reportId: string) =>
      request<Report>(`/reports/${reportId}`),
  },
}
