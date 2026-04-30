from __future__ import annotations

# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.


from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_chaos_agent.models.scenario import Severity


class TrendPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SeverityTrend(BaseModel):
    period: str
    date: str
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    total: int = 0


class EndpointRiskScore(BaseModel):
    endpoint_path: str
    endpoint_method: str
    risk_score: float = Field(ge=0.0, le=100.0)
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    last_tested_at: datetime | None = None


class ComparisonResult(BaseModel):
    baseline_report_id: str
    comparison_report_id: str
    new_findings: int = 0
    resolved_findings: int = 0
    persistent_findings: int = 0
    severity_changes: dict[str, dict[str, int]] = Field(default_factory=dict)
    new_vulnerability_details: list[dict[str, Any]] = Field(default_factory=list)
    resolved_vulnerability_details: list[dict[str, Any]] = Field(default_factory=list)
    risk_score_delta: float = 0.0
    improved: bool = True


class AnalyticsSummary(BaseModel):
    tenant_id: str = ""
    period: TrendPeriod = TrendPeriod.WEEKLY
    total_executions: int = 0
    total_scenarios_run: int = 0
    total_vulnerabilities: int = 0
    severity_distribution: dict[str, int] = Field(default_factory=dict)
    top_risk_endpoints: list[EndpointRiskScore] = Field(default_factory=list)
    trends: list[SeverityTrend] = Field(default_factory=list)
    pass_rate: float = Field(default=0.0, description="Percentage of scenarios with no vulnerability")
    avg_execution_time_ms: float = 0.0
