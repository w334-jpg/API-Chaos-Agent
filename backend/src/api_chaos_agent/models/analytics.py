"""Analytics models.

Defines the data structures for analytics summaries, severity trends,
endpoint risk scores, and report comparisons.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_chaos_agent.models.scenario import Severity


class TrendPeriod(str, Enum):
    """Time period for trend analysis."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SeverityTrend(BaseModel):
    """Severity distribution for a single time period."""

    period: str = Field(description="Time period label")
    date: str = Field(description="Date of the trend data point")
    critical: int = Field(default=0, description="Number of critical findings")
    high: int = Field(default=0, description="Number of high findings")
    medium: int = Field(default=0, description="Number of medium findings")
    low: int = Field(default=0, description="Number of low findings")
    info: int = Field(default=0, description="Number of informational findings")
    total: int = Field(default=0, description="Total findings in this period")


class EndpointRiskScore(BaseModel):
    """Risk score for a specific API endpoint."""

    endpoint_path: str = Field(description="API endpoint path")
    endpoint_method: str = Field(description="HTTP method")
    risk_score: float = Field(ge=0.0, le=100.0, description="Risk score (0-100)")
    total_findings: int = Field(default=0, description="Total number of findings")
    critical_count: int = Field(default=0, description="Number of critical findings")
    high_count: int = Field(default=0, description="Number of high findings")
    last_tested_at: datetime | None = Field(default=None, description="Last test timestamp")


class ComparisonResult(BaseModel):
    """Result of comparing two chaos test reports."""

    baseline_report_id: str = Field(description="Baseline report identifier")
    comparison_report_id: str = Field(description="Comparison report identifier")
    new_findings: int = Field(default=0, description="Findings present in comparison but not baseline")
    resolved_findings: int = Field(default=0, description="Findings resolved since baseline")
    persistent_findings: int = Field(default=0, description="Findings present in both reports")
    severity_changes: dict[str, dict[str, int]] = Field(default_factory=dict, description="Severity count changes between reports")
    new_vulnerability_details: list[dict[str, Any]] = Field(default_factory=list, description="Details of new vulnerabilities")
    resolved_vulnerability_details: list[dict[str, Any]] = Field(default_factory=list, description="Details of resolved vulnerabilities")
    risk_score_delta: float = Field(default=0.0, description="Change in overall risk score")
    improved: bool = Field(default=True, description="Whether security posture improved")


class AnalyticsSummary(BaseModel):
    """Aggregated analytics summary for a tenant."""

    tenant_id: str = Field(default="", description="Tenant identifier")
    period: TrendPeriod = Field(default=TrendPeriod.WEEKLY, description="Aggregation period")
    total_executions: int = Field(default=0, description="Total test executions in the period")
    total_scenarios_run: int = Field(default=0, description="Total scenarios executed")
    total_vulnerabilities: int = Field(default=0, description="Total vulnerabilities found")
    severity_distribution: dict[str, int] = Field(default_factory=dict, description="Vulnerability count by severity")
    top_risk_endpoints: list[EndpointRiskScore] = Field(default_factory=list, description="Endpoints ranked by risk score")
    trends: list[SeverityTrend] = Field(default_factory=list, description="Severity trends over time")
    pass_rate: float = Field(default=0.0, description="Percentage of scenarios with no vulnerability")
    avg_execution_time_ms: float = Field(default=0.0, description="Average execution time in milliseconds")
