from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_chaos_agent.models.scenario import ChaosScenario, Severity
from api_chaos_agent.models.schema import Endpoint


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ExecutionConfig(BaseModel):
    base_url: str
    concurrency: int = Field(default=10, ge=1, le=1000)
    timeout_seconds: float = Field(default=30.0, ge=1.0)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_delay_seconds: float = Field(default=1.0, ge=0.0)
    headers: dict[str, str] = Field(default_factory=dict)
    proxy: str | None = None
    serial: bool = Field(default=False, description="True=serial, False=parallel")


class ResponseData(BaseModel):
    status_code: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    elapsed_ms: float = 0.0
    error: str | None = None


class ScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_type: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    response: ResponseData = Field(default_factory=ResponseData)
    severity: Severity = Severity.MEDIUM
    vulnerability_found: bool = False
    details: str = ""


class TestResult(BaseModel):
    __test__ = False
    id: str = Field(default_factory=lambda: "")
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    total_scenarios: int = 0
    completed_scenarios: int = 0
    failed_scenarios: int = 0
    results: list[ScenarioResult] = Field(default_factory=list)
    config: ExecutionConfig | None = None


class Finding(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_type: str
    endpoint_path: str
    endpoint_method: str
    severity: Severity
    vulnerability_found: bool
    description: str
    reproduction_steps: list[str] = Field(default_factory=list)
    remediation: str = ""
    response_snapshot: dict[str, Any] = Field(default_factory=dict)


class Report(BaseModel):
    id: str = Field(default_factory=lambda: "")
    title: str = "API Chaos Test Report"
    generated_at: datetime = Field(default_factory=datetime.now)
    total_scenarios: int = 0
    vulnerabilities_found: int = 0
    execution_time_ms: float = 0.0
    severity_summary: dict[str, int] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    test_result: TestResult | None = None
