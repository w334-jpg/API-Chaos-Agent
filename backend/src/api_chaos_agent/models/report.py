"""Report and execution result models.

Defines the data structures for chaos test results, findings, and
generated reports.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_chaos_agent.models.scenario import ChaosScenario, Severity
from api_chaos_agent.models.schema import Endpoint


class ExecutionStatus(str, Enum):
    """Status of a chaos test execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ExecutionConfig(BaseModel):
    """Configuration for a chaos test execution run."""

    base_url: str = Field(description="Target API base URL")
    concurrency: int = Field(default=10, ge=1, le=1000, description="Maximum concurrent scenario executions")
    timeout_seconds: float = Field(default=30.0, ge=1.0, description="Per-scenario timeout in seconds")
    max_retries: int = Field(default=2, ge=0, le=10, description="Maximum retry attempts per scenario")
    retry_delay_seconds: float = Field(default=1.0, ge=0.0, description="Delay between retries in seconds")
    headers: dict[str, str] = Field(default_factory=dict, description="Default HTTP headers for all requests")
    proxy: str | None = Field(default=None, description="HTTP proxy URL")
    serial: bool = Field(default=False, description="True=serial execution, False=parallel execution")


class ResponseData(BaseModel):
    """Captured HTTP response data from a chaos scenario execution."""

    status_code: int | None = Field(default=None, description="HTTP response status code")
    headers: dict[str, str] = Field(default_factory=dict, description="Response headers")
    body: Any = Field(default=None, description="Response body (parsed JSON or raw text)")
    elapsed_ms: float = Field(default=0.0, description="Request duration in milliseconds")
    error: str | None = Field(default=None, description="Error message if request failed")


class ScenarioResult(BaseModel):
    """Result of a single chaos scenario execution."""

    scenario_id: str = Field(description="Unique scenario identifier")
    scenario_name: str = Field(description="Human-readable scenario name")
    scenario_type: str = Field(description="Type of chaos scenario")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING, description="Execution status")
    response: ResponseData = Field(default_factory=ResponseData, description="Captured HTTP response")
    severity: Severity = Field(default=Severity.MEDIUM, description="Severity level of the finding")
    vulnerability_found: bool = Field(default=False, description="Whether a vulnerability was detected")
    details: str = Field(default="", description="Additional details about the result")


class TestResult(BaseModel):
    """Aggregated result of a complete chaos test run."""

    __test__ = False  # Prevent pytest from collecting this class

    id: str = Field(default_factory=lambda: "", description="Unique test run identifier")
    started_at: datetime = Field(default_factory=datetime.now, description="Timestamp when test started")
    completed_at: datetime | None = Field(default=None, description="Timestamp when test completed")
    total_scenarios: int = Field(default=0, description="Total number of scenarios in the test")
    completed_scenarios: int = Field(default=0, description="Number of successfully completed scenarios")
    failed_scenarios: int = Field(default=0, description="Number of failed scenarios")
    results: list[ScenarioResult] = Field(default_factory=list, description="Individual scenario results")
    config: ExecutionConfig | None = Field(default=None, description="Execution configuration used")


class Finding(BaseModel):
    """A security or resilience finding from a chaos test."""

    scenario_id: str = Field(description="Scenario that produced the finding")
    scenario_name: str = Field(description="Human-readable scenario name")
    scenario_type: str = Field(description="Type of chaos scenario")
    endpoint_path: str = Field(description="API endpoint path tested")
    endpoint_method: str = Field(description="HTTP method used")
    severity: Severity = Field(description="Severity level of the finding")
    vulnerability_found: bool = Field(description="Whether a vulnerability was confirmed")
    details: str = Field(default="", description="Detailed description of the finding")
    recommendation: str = Field(default="", description="Recommended remediation action")
    response_status: int | None = Field(default=None, description="HTTP status code observed")
    expected_behavior: str = Field(default="", description="Expected API behavior")
    actual_behavior: str = Field(default="", description="Actual API behavior observed")


class ReportSummary(BaseModel):
    """Summary statistics for a chaos test report."""

    total_endpoints: int = Field(default=0, description="Total number of endpoints tested")
    total_scenarios: int = Field(default=0, description="Total scenarios executed")
    passed: int = Field(default=0, description="Scenarios that passed (no vulnerability)")
    failed: int = Field(default=0, description="Scenarios that detected vulnerabilities")
    errors: int = Field(default=0, description="Scenarios that encountered errors")
    severity_counts: dict[str, int] = Field(default_factory=dict, description="Count of findings by severity")
    vulnerability_rate: float = Field(default=0.0, description="Percentage of scenarios that found vulnerabilities")


class Report(BaseModel):
    """Complete chaos test report."""

    id: str = Field(description="Unique report identifier")
    schema_id: str = Field(description="API schema that was tested")
    created_at: datetime = Field(default_factory=datetime.now, description="Report generation timestamp")
    summary: ReportSummary = Field(default_factory=ReportSummary, description="Aggregated summary")
    findings: list[Finding] = Field(default_factory=list, description="Security and resilience findings")
    test_result: TestResult | None = Field(default=None, description="Full test result data")
    tenant_id: str = Field(default="", description="Owning tenant identifier")
