/** Graceful degradation utilities for API failures. */

interface DegradedResult<T> {
  data: T | null
  degraded: boolean
  reason?: string
}

export function withDegradation<T>(
  value: unknown,
  guard: (v: unknown) => v is T,
  fallback: T,
  label = "data",
): DegradedResult<T> {
  if (guard(value)) {
    return { data: value, degraded: false }
  }
  console.warn(`[Degradation] ${label} failed validation, using fallback`)
  return { data: fallback, degraded: true, reason: `Invalid ${label} structure from API` }
}

export function createRetryWithBackoff(
  baseDelay = 1000,
  maxRetries = 3,
  maxDelay = 30000,
) {
  return async function retryWithBackoff<T>(
    fn: () => Promise<T>,
    retries = maxRetries,
  ): Promise<T> {
    let lastError: Error | null = null
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        return await fn()
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err))
        if (attempt < retries) {
          const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay)
          const jitter = Math.random() * 200
          await new Promise((resolve) => setTimeout(resolve, delay + jitter))
        }
      }
    }
    throw lastError ?? new Error("Retry failed")
  }
}

export function isOffline(): boolean {
  return typeof navigator !== "undefined" && !navigator.onLine
}

export function getApiErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    if (err.message === "Request cancelled") return "请求已取消"
    if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
      return "网络连接失败，请检查网络设置"
    }
    return err.message
  }
  return "未知错误"
}
