/** Runtime type guards for API response validation. */

import type {
  ApiEndpoint,
  Scenario,
  Execution,
  Report,
  HealthStatus,
  UploadResponse,
  ParseResponse,
} from "@/types"

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function isHealthStatus(value: unknown): value is HealthStatus {
  if (!isObject(value)) return false
  return typeof value.status === "string"
}

export function isUploadResponse(value: unknown): value is UploadResponse {
  if (!isObject(value)) return false
  return typeof value.schema_id === "string"
}

export function isParseResponse(value: unknown): value is ParseResponse {
  if (!isObject(value)) return false
  return typeof value.schema_id === "string" && Array.isArray(value.endpoints)
}

export function isApiEndpoint(value: unknown): value is ApiEndpoint {
  if (!isObject(value)) return false
  return typeof value.method === "string" && typeof value.path === "string"
}

export function isScenario(value: unknown): value is Scenario {
  if (!isObject(value)) return false
  return typeof value.id === "string" && typeof value.name === "string"
}

export function isExecution(value: unknown): value is Execution {
  if (!isObject(value)) return false
  return typeof value.id === "string" && typeof value.status === "string"
}

export function isReport(value: unknown): value is Report {
  if (!isObject(value)) return false
  return typeof value.id === "string" && typeof value.schema_id === "string" && isObject(value.summary)
}

export function isApiError(value: unknown): value is { error: { type: string; detail: string; status: number } } {
  if (!isObject(value)) return false
  const err = value.error
  return isObject(err) && typeof err.type === "string" && typeof err.detail === "string"
}

export function ensureArray<T>(value: unknown, guard: (v: unknown) => v is T): T[] {
  if (!Array.isArray(value)) return []
  return value.filter(guard)
}

export function withFallback<T>(value: unknown, guard: (v: unknown) => v is T, fallback: T): T {
  return guard(value) ? value : fallback
}
