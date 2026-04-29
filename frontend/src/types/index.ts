export type Severity = "critical" | "high" | "medium" | "low" | "info"

export type ScenarioType = "auth_bypass" | "injection" | "rate_limit" | "data_leak" | "error_handling" | "input_validation" | "ssl_tls" | "cors" | "dos" | "business_logic"

export type ExecutionStatus = "pending" | "running" | "completed" | "failed" | "cancelled"

export interface ApiEndpoint {
  method: string
  path: string
  summary?: string
  parameters?: ApiParameter[]
  request_body?: ApiRequestBody
  responses?: Record<string, ApiResponse>
}

export interface ApiParameter {
  name: string
  location: "query" | "header" | "path" | "cookie"
  required: boolean
  schema?: Record<string, unknown>
  description?: string
}

export interface ApiRequestBody {
  content_type: string
  schema?: Record<string, unknown>
  required: boolean
}

export interface ApiResponse {
  description?: string
  content_type?: string
  schema?: Record<string, unknown>
}

export interface Schema {
  id: string
  filename: string
  upload_time: string
  endpoint_count: number
  title?: string
  version?: string
}

export interface Scenario {
  id: string
  schema_id: string
  endpoint: string
  method: string
  type: ScenarioType
  name: string
  description: string
  severity: Severity
  parameters?: Record<string, unknown>
  expected_behavior?: string
  created_at: string
}

export interface Execution {
  id: string
  scenario_ids: string[]
  status: ExecutionStatus
  started_at: string
  completed_at?: string
  progress: number
  total: number
  results?: ExecutionResult[]
}

export interface ExecutionResult {
  scenario_id: string
  passed: boolean
  severity: Severity
  finding?: string
  details?: string
  request?: string
  response?: string
  duration_ms?: number
}

export interface Report {
  id: string
  execution_id: string
  generated_at: string
  summary: ReportSummary
  findings: ReportFinding[]
}

export interface ReportSummary {
  total_scenarios: number
  passed: number
  failed: number
  severity_breakdown: Record<Severity, number>
}

export interface ReportFinding {
  id: string
  scenario_id: string
  endpoint: string
  method: string
  scenario_type: ScenarioType
  severity: Severity
  title: string
  description: string
  details?: string
  recommendation?: string
}

export interface HealthStatus {
  status: string
  version?: string
  uptime?: number
}

export interface UploadResponse {
  schema_id: string
  filename: string
  message: string
}

export interface ParseResponse {
  schema_id: string
  endpoints: ApiEndpoint[]
  title?: string
  version?: string
}

export interface GenerateScenariosRequest {
  schema_id: string
  endpoint?: string
  method?: string
  scenario_types?: ScenarioType[]
}

export interface GenerateBatchRequest {
  schema_id: string
  scenario_types?: ScenarioType[]
}

export interface RunExecutionRequest {
  scenario_ids: string[]
  base_url?: string
  headers?: Record<string, string>
}

export interface GenerateReportRequest {
  execution_id: string
}
