export type ChaosScenarioType =
  | "latency_injection"
  | "error_status_code"
  | "request_tampering"
  | "rate_limit_burst";

export type Severity = "critical" | "high" | "medium" | "low";

export interface ChaosScenario {
  id: string;
  name: string;
  type: ChaosScenarioType;
  endpoint: string;
  method: string;
  configuration: ScenarioConfiguration;
  description: string;
}

export interface ScenarioConfiguration {
  latency_ms?: number;
  status_code?: number;
  tampered_fields?: Record<string, unknown>;
  burst_count?: number;
  burst_interval_ms?: number;
  headers?: Record<string, string>;
  body?: Record<string, unknown>;
}

export interface ExecutionConfig {
  mode: "serial" | "parallel";
  concurrency: number;
  timeout_ms: number;
  retry_count: number;
  retry_delay_ms: number;
  proxy_url?: string;
}

export interface TestResult {
  scenario_id: string;
  status: "success" | "failure" | "error" | "timeout";
  status_code?: number;
  latency_ms: number;
  response_body?: unknown;
  error_message?: string;
  timestamp: number;
}

export interface Finding {
  scenario: ChaosScenario;
  result: TestResult;
  severity: Severity;
  description: string;
  remediation: string;
  reproduction_steps: string[];
}

export interface Report {
  id: string;
  created_at: string;
  summary: ReportSummary;
  findings: Finding[];
}

export interface ReportSummary {
  total_scenarios: number;
  passed: number;
  failed: number;
  errors: number;
  by_severity: Record<Severity, number>;
  avg_latency_ms: number;
}
