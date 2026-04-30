"""Unit tests for Phase 2: Analytics Service."""

import pytest
import time

from api_chaos_agent.models.analytics import TrendPeriod
from api_chaos_agent.models.report import Report, Finding
from api_chaos_agent.models.scenario import Severity
from api_chaos_agent.services.analytics_service import AnalyticsService


def _make_report(vulns: list[dict], exec_time_ms: float = 100.0) -> Report:
    findings = [
        Finding(
            scenario_id=v.get("scenario_id", f"scenario-{i}"),
            scenario_name=v.get("scenario_name", "Test Scenario"),
            scenario_type=v.get("type", "latency_injection"),
            endpoint_path=v.get("path", "/api/test"),
            endpoint_method=v.get("method", "GET"),
            severity=Severity(v.get("severity", "medium")),
            vulnerability_found=True,
            description=v.get("description", "Test finding"),
        )
        for i, v in enumerate(vulns)
    ]
    return Report(
        id=f"report-{int(time.monotonic()*1000)}",
        total_scenarios=10,
        execution_time_ms=exec_time_ms,
        findings=findings,
    )


class TestAnalyticsService:
    def setup_method(self):
        self.service = AnalyticsService()

    def test_empty_summary(self):
        summary = self.service.get_summary("nonexistent")
        assert summary.total_executions == 0
        assert summary.total_vulnerabilities == 0

    def test_summary_with_reports(self):
        report = _make_report([
            {"severity": "critical", "path": "/api/users"},
            {"severity": "high", "path": "/api/orders"},
            {"severity": "medium", "path": "/api/products"},
        ])
        self.service.store_report("tenant-1", report)
        summary = self.service.get_summary("tenant-1")
        assert summary.total_executions == 1
        assert summary.total_vulnerabilities == 3
        assert summary.severity_distribution.get("critical") == 1
        assert summary.severity_distribution.get("high") == 1

    def test_endpoint_risk_scoring(self):
        report = _make_report([
            {"severity": "critical", "path": "/api/users"},
            {"severity": "critical", "path": "/api/users"},
            {"severity": "high", "path": "/api/orders"},
        ])
        self.service.store_report("tenant-2", report)
        summary = self.service.get_summary("tenant-2")
        assert len(summary.top_risk_endpoints) >= 1
        top = summary.top_risk_endpoints[0]
        assert top.endpoint_path == "/api/users"
        assert top.risk_score > 0

    def test_compare_reports_improved(self):
        baseline = _make_report([
            {"severity": "critical", "path": "/api/users"},
            {"severity": "high", "path": "/api/orders"},
        ])
        comparison = _make_report([
            {"severity": "medium", "path": "/api/users"},
        ])
        result = self.service.compare_reports(baseline, comparison)
        assert result.resolved_findings >= 1
        assert result.new_findings >= 0
        assert result.improved is True

    def test_compare_reports_regressed(self):
        baseline = _make_report([
            {"severity": "low", "path": "/api/health"},
        ])
        comparison = _make_report([
            {"severity": "low", "path": "/api/health"},
            {"severity": "critical", "path": "/api/payments"},
            {"severity": "high", "path": "/api/auth"},
        ])
        result = self.service.compare_reports(baseline, comparison)
        assert result.new_findings >= 2
        assert result.improved is False

    def test_pass_rate_calculation(self):
        report = _make_report([], exec_time_ms=200.0)
        report.total_scenarios = 100
        self.service.store_report("tenant-3", report)
        summary = self.service.get_summary("tenant-3")
        assert summary.pass_rate == 100.0

    def test_avg_execution_time(self):
        r1 = _make_report([], exec_time_ms=100.0)
        r2 = _make_report([], exec_time_ms=200.0)
        self.service.store_report("tenant-4", r1)
        self.service.store_report("tenant-4", r2)
        summary = self.service.get_summary("tenant-4")
        assert summary.avg_execution_time_ms == 150.0
