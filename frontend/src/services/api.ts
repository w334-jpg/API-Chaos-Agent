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
const API_VERSION = "v1"
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 1000

const activeControllers = new Map<string, AbortController>()

function createAbortController(id: string): AbortController {
  const existing = activeControllers.get(id)
  if (existing) {
    existing.abort()
  }
  const controller = new AbortController()
  activeControllers.set(id, controller)
  return controller
}

function removeAbortController(id: string): void {
  activeControllers.delete(id)
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function request<T>(
  url: string,
  options?: RequestInit & { requestId?: string; retries?: number },
): Promise<T> {
  const { requestId, retries = MAX_RETRIES, ...fetchOptions } = options || {}
  const controller = requestId ? createAbortController(requestId) : undefined

  let lastError: Error | null = null

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(`${API_BASE}/${API_VERSION}${url}`, {
        headers: {
          "Content-Type": "application/json",
          "X-API-Version": API_VERSION,
          ...fetchOptions.headers,
        },
        signal: controller?.signal,
        ...fetchOptions,
      })

      if (response.status === 429) {
        const retryAfter = response.headers.get("Retry-After")
        const delay = retryAfter ? parseInt(retryAfter, 10) * 1000 : RETRY_DELAY_MS
        await sleep(delay)
        continue
      }

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      if (requestId) removeAbortController(requestId)
      return response.json()
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new Error("Request cancelled")
      }
      lastError = err instanceof Error ? err : new Error(String(err))
      if (attempt < retries && !lastError.message.includes("HTTP 4")) {
        await sleep(RETRY_DELAY_MS * (attempt + 1))
        continue
      }
    }
  }

  if (requestId) removeAbortController(requestId)
  throw lastError || new Error("Request failed after retries")
}

export function cancelRequest(requestId: string): void {
  const controller = activeControllers.get(requestId)
  if (controller) {
    controller.abort()
    removeAbortController(requestId)
  }
}

export const api = {
  health: {
    check: () => request<HealthStatus>("/health"),
  },

  schema: {
    upload: async (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      const response = await fetch(`${API_BASE}/${API_VERSION}/schema/upload`, {
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
        requestId: `scenario-generate-${data.schema_id}`,
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
        requestId: `execution-run-${Date.now()}`,
      }),

    getStatus: (executionId: string) =>
      request<Execution>(`/execution/${executionId}/status`),

    cancel: (executionId: string) => cancelRequest(`execution-run-${executionId}`),
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
