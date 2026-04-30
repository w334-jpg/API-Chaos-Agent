# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""Analytics service for advanced reporting, trend analysis, and history comparison.

Provides:
- Severity trend analysis across time periods
- Endpoint risk scoring
- Report comparison (baseline vs. current)
- Tenant-level analytics summaries
- Pass rate and execution time metrics
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.analytics import (
    AnalyticsSummary,
    ComparisonResult,
    EndpointRiskScore,
    SeverityTrend,
    TrendPeriod,
)
from api_chaos_agent.models.report import Report, Finding
from api_chaos_agent.models.scenario import Severity

logger = get_logger(__name__)

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


class AnalyticsService:
    """Generate analytics from execution reports."""

    def __init__(self) -> None:
        self._reports: dict[str, list[Report]] = {}

    def store_report(self, tenant_id: str, report: Report) -> None:
        self._reports.setdefault(tenant_id, []).append(report)

    def get_summary(self, tenant_id: str, period: TrendPeriod = TrendPeriod.WEEKLY) -> AnalyticsSummary:
        reports = self._reports.get(tenant_id, [])
        if not reports:
            return AnalyticsSummary(tenant_id=tenant_id, period=period)

        total_executions = len(reports)
        total_scenarios = sum(r.total_scenarios for r in reports)
        all_findings: list[Finding] = []
        for r in reports:
            all_findings.extend(r.findings)

        severity_dist: dict[str, int] = defaultdict(int)
        for f in all_findings:
            severity_dist[f.severity.value if isinstance(f.severity, Severity) else str(f.severity)] += 1

        top_risks = self._compute_endpoint_risks(all_findings)
        trends = self._compute_trends(reports, period)
        pass_rate = self._compute_pass_rate(reports)
        avg_time = self._compute_avg_execution_time(reports)

        return AnalyticsSummary(
            tenant_id=tenant_id,
            period=period,
            total_executions=total_executions,
            total_scenarios_run=total_scenarios,
            total_vulnerabilities=len(all_findings),
            severity_distribution=dict(severity_dist),
            top_risk_endpoints=top_risks[:10],
            trends=trends,
            pass_rate=pass_rate,
            avg_execution_time_ms=avg_time,
        )

    def compare_reports(self, baseline: Report, comparison: Report) -> ComparisonResult:
        baseline_keys = self._finding_keys(baseline.findings)
        comparison_keys = self._finding_keys(comparison.findings)

        new_keys = comparison_keys - baseline_keys
        resolved_keys = baseline_keys - comparison_keys
        persistent_keys = baseline_keys & comparison_keys

        new_findings = [f for f in comparison.findings if self._finding_key(f) in new_keys]
        resolved_findings = [f for f in baseline.findings if self._finding_key(f) in resolved_keys]

        severity_changes = self._compute_severity_changes(
            baseline.findings,
            comparison.findings,
        )

        baseline_score = self._compute_risk_score(baseline)
        comparison_score = self._compute_risk_score(comparison)

        return ComparisonResult(
            baseline_report_id=baseline.id,
            comparison_report_id=comparison.id,
            new_findings=len(new_keys),
            resolved_findings=len(resolved_keys),
            persistent_findings=len(persistent_keys),
            severity_changes=severity_changes,
            new_vulnerability_details=[self._finding_to_dict(f) for f in new_findings],
            resolved_vulnerability_details=[self._finding_to_dict(f) for f in resolved_findings],
            risk_score_delta=comparison_score - baseline_score,
            improved=comparison_score <= baseline_score,
        )

    def _compute_endpoint_risks(self, findings: list[Finding]) -> list[EndpointRiskScore]:
        endpoint_data: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "total": 0, "critical": 0, "high": 0, "score": 0.0, "last_tested": None,
        })
        for f in findings:
            key = f"{f.endpoint_method}:{f.endpoint_path}"
            data = endpoint_data[key]
            data["total"] += 1
            sev = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            if sev == "critical":
                data["critical"] += 1
                data["score"] += 25
            elif sev == "high":
                data["high"] += 1
                data["score"] += 10
            elif sev == "medium":
                data["score"] += 3
            elif sev == "low":
                data["score"] += 1
        results: list[EndpointRiskScore] = []
        for key, data in endpoint_data.items():
            method, path = key.split(":", 1)
            results.append(EndpointRiskScore(
                endpoint_path=path,
                endpoint_method=method,
                risk_score=min(data["score"], 100.0),
                total_findings=data["total"],
                critical_count=data["critical"],
                high_count=data["high"],
            ))
        return sorted(results, key=lambda r: r.risk_score, reverse=True)

    def _compute_trends(self, reports: list[Report], period: TrendPeriod) -> list[SeverityTrend]:
        if not reports:
            return []
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in reports:
            date_key = r.generated_at.strftime("%Y-%m-%d" if period == TrendPeriod.DAILY else "%Y-W%W" if period == TrendPeriod.WEEKLY else "%Y-%m")
            for f in r.findings:
                sev = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
                grouped[date_key][sev] += 1
        trends: list[SeverityTrend] = []
        for date_key in sorted(grouped.keys()):
            counts = grouped[date_key]
            trends.append(SeverityTrend(
                period=period.value,
                date=date_key,
                critical=counts.get("critical", 0),
                high=counts.get("high", 0),
                medium=counts.get("medium", 0),
                low=counts.get("low", 0),
                info=counts.get("info", 0),
                total=sum(counts.values()),
            ))
        return trends

    def _compute_pass_rate(self, reports: list[Report]) -> float:
        if not reports:
            return 0.0
        total_scenarios = sum(r.total_scenarios for r in reports)
        total_vulns = sum(len(r.findings) for r in reports)
        if total_scenarios == 0:
            return 100.0
        return round((1.0 - total_vulns / total_scenarios) * 100, 2)

    def _compute_avg_execution_time(self, reports: list[Report]) -> float:
        if not reports:
            return 0.0
        times = [r.execution_time_ms for r in reports if r.execution_time_ms > 0]
        return round(sum(times) / len(times), 2) if times else 0.0

    def _compute_risk_score(self, report: Report) -> float:
        score = 0.0
        for f in report.findings:
            sev = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            weight = {"critical": 25, "high": 10, "medium": 3, "low": 1, "info": 0}.get(sev, 0)
            score += weight
        return min(score, 100.0)

    def _finding_key(self, f: Finding) -> str:
        return f"{f.endpoint_method}:{f.endpoint_path}:{f.scenario_type}"

    def _finding_keys(self, findings: list[Finding]) -> set[str]:
        return {self._finding_key(f) for f in findings}

    def _finding_to_dict(self, f: Finding) -> dict[str, Any]:
        return {
            "endpoint": f"{f.endpoint_method} {f.endpoint_path}",
            "scenario_type": f.scenario_type,
            "severity": f.severity.value if isinstance(f.severity, Severity) else str(f.severity),
            "description": f.description,
        }

    def _compute_severity_changes(
        self, baseline: list[Finding], comparison: list[Finding]
    ) -> dict[str, dict[str, int]]:
        changes: dict[str, dict[str, int]] = {"increased": {}, "decreased": {}, "unchanged": {}}
        baseline_sevs: dict[str, str] = {}
        for f in baseline:
            key = self._finding_key(f)
            baseline_sevs[key] = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
        for f in comparison:
            key = self._finding_key(f)
            comp_sev = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            if key in baseline_sevs:
                base_level = _SEVERITY_ORDER.get(baseline_sevs[key], 0)
                comp_level = _SEVERITY_ORDER.get(comp_sev, 0)
                if comp_level > base_level:
                    changes["increased"][comp_sev] = changes["increased"].get(comp_sev, 0) + 1
                elif comp_level < base_level:
                    changes["decreased"][comp_sev] = changes["decreased"].get(comp_sev, 0) + 1
                else:
                    changes["unchanged"][comp_sev] = changes["unchanged"].get(comp_sev, 0) + 1
        return changes
