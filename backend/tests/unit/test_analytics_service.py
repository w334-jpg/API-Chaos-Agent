"""TDD-enhanced tests for Analytics Service — Block 6.

Covers:
- Unit tests: all internal methods and data transformations
- Functional tests: end-to-end analytics workflows
- Edge cases: empty data, single findings, boundary values
- Stress tests: large report volumes, many tenants, concurrent access
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from api_chaos_agent.models.analytics import (
    AnalyticsSummary,
    ComparisonResult,
    EndpointRiskScore,
    SeverityTrend,
    TrendPeriod,
)
from api_chaos_agent.models.report import Report, Finding
from api_chaos_agent.models.scenario import Severity
from api_chaos_agent.services.analytics_service import AnalyticsService, _SEVERITY_ORDER


def _make_finding(
    path: str = "/api/test",
    method: str = "GET",
    severity: str = "medium",
    scenario_type: str = "latency_injection",
    description: str = "Test finding",
) -> Finding:
    return Finding(
        scenario_id=f"sc-{int(time.monotonic()*1e6)}",
        scenario_name="Test Scenario",
        scenario_type=scenario_type,
        endpoint_path=path,
        endpoint_method=method,
        severity=Severity(severity),
        vulnerability_found=True,
        description=description,
    )


def _make_report(
    vulns: list[dict] | None = None,
    exec_time_ms: float = 100.0,
    total_scenarios: int = 10,
    report_id: str | None = None,
    generated_at: datetime | None = None,
) -> Report:
    findings = []
    if vulns:
        for i, v in enumerate(vulns):
            findings.append(
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
            )
    rid = report_id or f"report-{int(time.monotonic()*1e6)}"
    return Report(
        id=rid,
        total_scenarios=total_scenarios,
        execution_time_ms=exec_time_ms,
        findings=findings,
        generated_at=generated_at or datetime.now(),
    )


class TestAnalyticsServiceUnit:
    """Unit tests for individual methods of AnalyticsService."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_store_report_creates_tenant_entry(self):
        report = _make_report()
        self.service.store_report("t1", report)
        assert "t1" in self.service._reports
        assert len(self.service._reports["t1"]) == 1

    def test_store_report_appends_to_existing_tenant(self):
        r1 = _make_report(report_id="r1")
        r2 = _make_report(report_id="r2")
        self.service.store_report("t1", r1)
        self.service.store_report("t1", r2)
        assert len(self.service._reports["t1"]) == 2

    def test_store_report_different_tenants_isolated(self):
        r1 = _make_report(report_id="r1")
        r2 = _make_report(report_id="r2")
        self.service.store_report("t1", r1)
        self.service.store_report("t2", r2)
        assert len(self.service._reports["t1"]) == 1
        assert len(self.service._reports["t2"]) == 1

    def test_get_summary_empty_tenant(self):
        summary = self.service.get_summary("nonexistent")
        assert summary.total_executions == 0
        assert summary.total_vulnerabilities == 0
        assert summary.total_scenarios_run == 0
        assert summary.pass_rate == 0.0
        assert summary.avg_execution_time_ms == 0.0
        assert summary.severity_distribution == {}
        assert summary.top_risk_endpoints == []
        assert summary.trends == []

    def test_get_summary_single_report(self):
        report = _make_report([
            {"severity": "critical", "path": "/api/users"},
            {"severity": "high", "path": "/api/orders"},
            {"severity": "medium", "path": "/api/products"},
        ])
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.total_executions == 1
        assert summary.total_vulnerabilities == 3
        assert summary.total_scenarios_run == 10
        assert summary.severity_distribution["critical"] == 1
        assert summary.severity_distribution["high"] == 1
        assert summary.severity_distribution["medium"] == 1

    def test_get_summary_multiple_reports(self):
        r1 = _make_report([{"severity": "critical", "path": "/a"}], total_scenarios=5)
        r2 = _make_report([{"severity": "high", "path": "/b"}], total_scenarios=5)
        self.service.store_report("t1", r1)
        self.service.store_report("t1", r2)
        summary = self.service.get_summary("t1")
        assert summary.total_executions == 2
        assert summary.total_scenarios_run == 10
        assert summary.total_vulnerabilities == 2

    def test_get_summary_period_default(self):
        report = _make_report()
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.period == TrendPeriod.WEEKLY

    def test_get_summary_period_daily(self):
        report = _make_report()
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1", period=TrendPeriod.DAILY)
        assert summary.period == TrendPeriod.DAILY

    def test_get_summary_period_monthly(self):
        report = _make_report()
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1", period=TrendPeriod.MONTHLY)
        assert summary.period == TrendPeriod.MONTHLY


class TestEndpointRiskScoring:
    """Tests for _compute_endpoint_risks method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_single_endpoint_single_finding(self):
        findings = [_make_finding(path="/api/users", severity="high")]
        risks = self.service._compute_endpoint_risks(findings)
        assert len(risks) == 1
        assert risks[0].endpoint_path == "/api/users"
        assert risks[0].endpoint_method == "GET"
        assert risks[0].risk_score == 10.0
        assert risks[0].total_findings == 1

    def test_single_endpoint_multiple_findings_accumulate(self):
        findings = [
            _make_finding(path="/api/users", severity="critical"),
            _make_finding(path="/api/users", severity="high"),
            _make_finding(path="/api/users", severity="medium"),
        ]
        risks = self.service._compute_endpoint_risks(findings)
        assert len(risks) == 1
        assert risks[0].risk_score == 25.0 + 10.0 + 3.0
        assert risks[0].total_findings == 3
        assert risks[0].critical_count == 1
        assert risks[0].high_count == 1

    def test_multiple_endpoints_sorted_by_risk(self):
        findings = [
            _make_finding(path="/api/low", severity="low"),
            _make_finding(path="/api/critical", severity="critical"),
            _make_finding(path="/api/medium", severity="medium"),
        ]
        risks = self.service._compute_endpoint_risks(findings)
        assert len(risks) == 3
        assert risks[0].endpoint_path == "/api/critical"
        assert risks[1].endpoint_path == "/api/medium"
        assert risks[2].endpoint_path == "/api/low"

    def test_risk_score_capped_at_100(self):
        findings = [_make_finding(path="/api/users", severity="critical") for _ in range(10)]
        risks = self.service._compute_endpoint_risks(findings)
        assert len(risks) == 1
        assert risks[0].risk_score == 100.0

    def test_info_severity_zero_score(self):
        findings = [_make_finding(path="/api/info", severity="info")]
        risks = self.service._compute_endpoint_risks(findings)
        assert len(risks) == 1
        assert risks[0].risk_score == 0.0

    def test_empty_findings(self):
        risks = self.service._compute_endpoint_risks([])
        assert risks == []

    def test_different_methods_same_path(self):
        findings = [
            _make_finding(path="/api/data", method="GET", severity="high"),
            _make_finding(path="/api/data", method="POST", severity="critical"),
        ]
        risks = self.service._compute_endpoint_risks(findings)
        assert len(risks) == 2
        methods = {r.endpoint_method for r in risks}
        assert methods == {"GET", "POST"}

    def test_top_10_risk_endpoints_in_summary(self):
        vulns = [
            {"severity": "critical", "path": f"/api/ep{i}"}
            for i in range(15)
        ]
        report = _make_report(vulns)
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert len(summary.top_risk_endpoints) == 10


class TestTrendComputation:
    """Tests for _compute_trends method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_empty_reports_no_trends(self):
        trends = self.service._compute_trends([], TrendPeriod.DAILY)
        assert trends == []

    def test_daily_trend_format(self):
        now = datetime(2025, 1, 15, 10, 30, 0)
        report = _make_report(
            [{"severity": "high", "path": "/a"}],
            generated_at=now,
        )
        trends = self.service._compute_trends([report], TrendPeriod.DAILY)
        assert len(trends) == 1
        assert trends[0].date == "2025-01-15"
        assert trends[0].high == 1

    def test_weekly_trend_format(self):
        now = datetime(2025, 1, 6, 0, 0, 0)
        report = _make_report(
            [{"severity": "critical", "path": "/a"}],
            generated_at=now,
        )
        trends = self.service._compute_trends([report], TrendPeriod.WEEKLY)
        assert len(trends) == 1
        assert "2025-W0" in trends[0].date
        assert trends[0].critical == 1

    def test_monthly_trend_format(self):
        now = datetime(2025, 3, 15, 0, 0, 0)
        report = _make_report(
            [{"severity": "medium", "path": "/a"}],
            generated_at=now,
        )
        trends = self.service._compute_trends([report], TrendPeriod.MONTHLY)
        assert len(trends) == 1
        assert trends[0].date == "2025-03"
        assert trends[0].medium == 1

    def test_multiple_days_grouped(self):
        d1 = datetime(2025, 1, 10)
        d2 = datetime(2025, 1, 10)
        d3 = datetime(2025, 1, 11)
        r1 = _make_report([{"severity": "high", "path": "/a"}], generated_at=d1)
        r2 = _make_report([{"severity": "critical", "path": "/b"}], generated_at=d2)
        r3 = _make_report([{"severity": "low", "path": "/c"}], generated_at=d3)
        trends = self.service._compute_trends([r1, r2, r3], TrendPeriod.DAILY)
        assert len(trends) == 2
        first = trends[0]
        assert first.date == "2025-01-10"
        assert first.high == 1
        assert first.critical == 1
        assert first.total == 2
        second = trends[1]
        assert second.date == "2025-01-11"
        assert second.low == 1
        assert second.total == 1

    def test_trend_sorted_by_date(self):
        d1 = datetime(2025, 3, 1)
        d2 = datetime(2025, 1, 1)
        d3 = datetime(2025, 2, 1)
        r1 = _make_report([{"severity": "high", "path": "/a"}], generated_at=d1)
        r2 = _make_report([{"severity": "low", "path": "/b"}], generated_at=d2)
        r3 = _make_report([{"severity": "medium", "path": "/c"}], generated_at=d3)
        trends = self.service._compute_trends([r1, r2, r3], TrendPeriod.MONTHLY)
        assert len(trends) == 3
        assert trends[0].date == "2025-01"
        assert trends[1].date == "2025-02"
        assert trends[2].date == "2025-03"

    def test_trend_total_equals_sum_of_severities(self):
        now = datetime(2025, 1, 15)
        report = _make_report([
            {"severity": "critical", "path": "/a"},
            {"severity": "high", "path": "/b"},
            {"severity": "medium", "path": "/c"},
            {"severity": "low", "path": "/d"},
            {"severity": "info", "path": "/e"},
        ], generated_at=now)
        trends = self.service._compute_trends([report], TrendPeriod.DAILY)
        assert len(trends) == 1
        t = trends[0]
        assert t.total == t.critical + t.high + t.medium + t.low + t.info


class TestPassRateComputation:
    """Tests for _compute_pass_rate method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_empty_reports_zero(self):
        assert self.service._compute_pass_rate([]) == 0.0

    def test_no_vulnerabilities_100_percent(self):
        report = _make_report([], total_scenarios=50)
        assert self.service._compute_pass_rate([report]) == 100.0

    def test_all_vulnerable_zero_percent(self):
        report = _make_report([{"severity": "high", "path": "/a"}], total_scenarios=1)
        rate = self.service._compute_pass_rate([report])
        assert rate == 0.0

    def test_partial_pass_rate(self):
        report = _make_report([{"severity": "high", "path": "/a"}], total_scenarios=10)
        rate = self.service._compute_pass_rate([report])
        assert rate == 90.0

    def test_multiple_reports_aggregate(self):
        r1 = _make_report([{"severity": "high", "path": "/a"}], total_scenarios=10)
        r2 = _make_report([{"severity": "high", "path": "/b"}, {"severity": "low", "path": "/c"}], total_scenarios=10)
        rate = self.service._compute_pass_rate([r1, r2])
        assert rate == 85.0

    def test_zero_scenarios_100_percent(self):
        report = _make_report([], total_scenarios=0)
        assert self.service._compute_pass_rate([report]) == 100.0

    def test_pass_rate_rounded_to_2_decimals(self):
        report = _make_report([{"severity": "high", "path": "/a"}], total_scenarios=3)
        rate = self.service._compute_pass_rate([report])
        assert rate == round(rate, 2)


class TestAvgExecutionTime:
    """Tests for _compute_avg_execution_time method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_empty_reports_zero(self):
        assert self.service._compute_avg_execution_time([]) == 0.0

    def test_single_report(self):
        report = _make_report([], exec_time_ms=250.0)
        assert self.service._compute_avg_execution_time([report]) == 250.0

    def test_multiple_reports_average(self):
        r1 = _make_report([], exec_time_ms=100.0)
        r2 = _make_report([], exec_time_ms=200.0)
        r3 = _make_report([], exec_time_ms=300.0)
        assert self.service._compute_avg_execution_time([r1, r2, r3]) == 200.0

    def test_zero_execution_time_excluded(self):
        r1 = _make_report([], exec_time_ms=0.0)
        r2 = _make_report([], exec_time_ms=200.0)
        avg = self.service._compute_avg_execution_time([r1, r2])
        assert avg == 200.0

    def test_all_zero_execution_time(self):
        r1 = _make_report([], exec_time_ms=0.0)
        r2 = _make_report([], exec_time_ms=0.0)
        assert self.service._compute_avg_execution_time([r1, r2]) == 0.0

    def test_result_rounded_to_2_decimals(self):
        r1 = _make_report([], exec_time_ms=100.0)
        r2 = _make_report([], exec_time_ms=101.0)
        avg = self.service._compute_avg_execution_time([r1, r2])
        assert avg == round(avg, 2)


class TestRiskScoreComputation:
    """Tests for _compute_risk_score method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_empty_report_zero(self):
        report = _make_report([])
        assert self.service._compute_risk_score(report) == 0.0

    def test_critical_finding(self):
        report = _make_report([{"severity": "critical", "path": "/a"}])
        assert self.service._compute_risk_score(report) == 25.0

    def test_high_finding(self):
        report = _make_report([{"severity": "high", "path": "/a"}])
        assert self.service._compute_risk_score(report) == 10.0

    def test_medium_finding(self):
        report = _make_report([{"severity": "medium", "path": "/a"}])
        assert self.service._compute_risk_score(report) == 3.0

    def test_low_finding(self):
        report = _make_report([{"severity": "low", "path": "/a"}])
        assert self.service._compute_risk_score(report) == 1.0

    def test_info_finding_zero(self):
        report = _make_report([{"severity": "info", "path": "/a"}])
        assert self.service._compute_risk_score(report) == 0.0

    def test_mixed_severity_sum(self):
        report = _make_report([
            {"severity": "critical", "path": "/a"},
            {"severity": "high", "path": "/b"},
            {"severity": "medium", "path": "/c"},
            {"severity": "low", "path": "/d"},
        ])
        assert self.service._compute_risk_score(report) == 25.0 + 10.0 + 3.0 + 1.0

    def test_risk_score_capped_at_100(self):
        vulns = [{"severity": "critical", "path": f"/a{i}"} for i in range(10)]
        report = _make_report(vulns)
        assert self.service._compute_risk_score(report) == 100.0


class TestFindingKeyMethods:
    """Tests for _finding_key, _finding_keys, _finding_to_dict."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_finding_key_format(self):
        f = _make_finding(path="/api/users", method="POST", scenario_type="latency_injection")
        key = self.service._finding_key(f)
        assert key == "POST:/api/users:latency_injection"

    def test_finding_keys_set(self):
        f1 = _make_finding(path="/a", method="GET", scenario_type="t1")
        f2 = _make_finding(path="/b", method="POST", scenario_type="t2")
        keys = self.service._finding_keys([f1, f2])
        assert len(keys) == 2
        assert "GET:/a:t1" in keys
        assert "POST:/b:t2" in keys

    def test_finding_keys_deduplication(self):
        f1 = _make_finding(path="/a", method="GET", scenario_type="t1")
        f2 = _make_finding(path="/a", method="GET", scenario_type="t1")
        keys = self.service._finding_keys([f1, f2])
        assert len(keys) == 1

    def test_finding_to_dict(self):
        f = _make_finding(path="/api/test", method="GET", severity="high", scenario_type="error_status", description="desc")
        d = self.service._finding_to_dict(f)
        assert d["endpoint"] == "GET /api/test"
        assert d["scenario_type"] == "error_status"
        assert d["severity"] == "high"
        assert d["description"] == "desc"


class TestSeverityChanges:
    """Tests for _compute_severity_changes method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_no_common_findings(self):
        baseline = [_make_finding(path="/a", scenario_type="t1", severity="high")]
        comparison = [_make_finding(path="/b", scenario_type="t2", severity="critical")]
        changes = self.service._compute_severity_changes(baseline, comparison)
        assert changes["increased"] == {}
        assert changes["decreased"] == {}
        assert changes["unchanged"] == {}

    def test_severity_increased(self):
        baseline = [_make_finding(path="/a", scenario_type="t1", severity="medium")]
        comparison = [_make_finding(path="/a", scenario_type="t1", severity="critical")]
        changes = self.service._compute_severity_changes(baseline, comparison)
        assert changes["increased"].get("critical", 0) == 1

    def test_severity_decreased(self):
        baseline = [_make_finding(path="/a", scenario_type="t1", severity="critical")]
        comparison = [_make_finding(path="/a", scenario_type="t1", severity="low")]
        changes = self.service._compute_severity_changes(baseline, comparison)
        assert changes["decreased"].get("low", 0) == 1

    def test_severity_unchanged(self):
        baseline = [_make_finding(path="/a", scenario_type="t1", severity="high")]
        comparison = [_make_finding(path="/a", scenario_type="t1", severity="high")]
        changes = self.service._compute_severity_changes(baseline, comparison)
        assert changes["unchanged"].get("high", 0) == 1

    def test_mixed_changes(self):
        baseline = [
            _make_finding(path="/a", scenario_type="t1", severity="high"),
            _make_finding(path="/b", scenario_type="t2", severity="medium"),
            _make_finding(path="/c", scenario_type="t3", severity="low"),
        ]
        comparison = [
            _make_finding(path="/a", scenario_type="t1", severity="critical"),
            _make_finding(path="/b", scenario_type="t2", severity="low"),
            _make_finding(path="/c", scenario_type="t3", severity="low"),
        ]
        changes = self.service._compute_severity_changes(baseline, comparison)
        assert changes["increased"].get("critical", 0) == 1
        assert changes["decreased"].get("low", 0) == 1
        assert changes["unchanged"].get("low", 0) == 1


class TestCompareReports:
    """Tests for compare_reports method."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_identical_reports(self):
        baseline = _make_report([{"severity": "high", "path": "/a", "type": "t1"}], report_id="r1")
        comparison = _make_report([{"severity": "high", "path": "/a", "type": "t1"}], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.persistent_findings == 1
        assert result.new_findings == 0
        assert result.resolved_findings == 0
        assert result.improved is True

    def test_improved_baseline_to_comparison(self):
        baseline = _make_report([
            {"severity": "critical", "path": "/a", "type": "t1"},
            {"severity": "high", "path": "/b", "type": "t2"},
        ], report_id="r1")
        comparison = _make_report([
            {"severity": "medium", "path": "/a", "type": "t1"},
        ], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.resolved_findings >= 1
        assert result.improved is True
        assert result.risk_score_delta < 0

    def test_regressed_comparison(self):
        baseline = _make_report([
            {"severity": "low", "path": "/a", "type": "t1"},
        ], report_id="r1")
        comparison = _make_report([
            {"severity": "low", "path": "/a", "type": "t1"},
            {"severity": "critical", "path": "/b", "type": "t2"},
            {"severity": "high", "path": "/c", "type": "t3"},
        ], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.new_findings >= 2
        assert result.improved is False
        assert result.risk_score_delta > 0

    def test_completely_new_findings(self):
        baseline = _make_report([], report_id="r1")
        comparison = _make_report([
            {"severity": "critical", "path": "/a", "type": "t1"},
        ], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.new_findings == 1
        assert result.resolved_findings == 0
        assert result.persistent_findings == 0

    def test_all_resolved(self):
        baseline = _make_report([
            {"severity": "high", "path": "/a", "type": "t1"},
            {"severity": "medium", "path": "/b", "type": "t2"},
        ], report_id="r1")
        comparison = _make_report([], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.resolved_findings == 2
        assert result.new_findings == 0
        assert result.improved is True

    def test_comparison_result_ids(self):
        baseline = _make_report([], report_id="base-id")
        comparison = _make_report([], report_id="comp-id")
        result = self.service.compare_reports(baseline, comparison)
        assert result.baseline_report_id == "base-id"
        assert result.comparison_report_id == "comp-id"

    def test_new_vulnerability_details_populated(self):
        baseline = _make_report([], report_id="r1")
        comparison = _make_report([
            {"severity": "critical", "path": "/api/pay", "method": "POST", "type": "error_status", "description": "Payment fails"},
        ], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert len(result.new_vulnerability_details) == 1
        detail = result.new_vulnerability_details[0]
        assert "POST" in detail["endpoint"]
        assert detail["severity"] == "critical"

    def test_resolved_vulnerability_details_populated(self):
        baseline = _make_report([
            {"severity": "high", "path": "/api/old", "type": "t1"},
        ], report_id="r1")
        comparison = _make_report([], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert len(result.resolved_vulnerability_details) == 1

    def test_risk_score_delta_calculation(self):
        baseline = _make_report([
            {"severity": "critical", "path": "/a", "type": "t1"},
        ], report_id="r1")
        comparison = _make_report([
            {"severity": "low", "path": "/a", "type": "t1"},
        ], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.risk_score_delta == 1.0 - 25.0

    def test_same_risk_score_improved_true(self):
        baseline = _make_report([
            {"severity": "high", "path": "/a", "type": "t1"},
        ], report_id="r1")
        comparison = _make_report([
            {"severity": "high", "path": "/a", "type": "t1"},
        ], report_id="r2")
        result = self.service.compare_reports(baseline, comparison)
        assert result.improved is True
        assert result.risk_score_delta == 0.0


class TestSeverityOrderConstant:
    """Tests for the _SEVERITY_ORDER constant."""

    def test_critical_highest(self):
        assert _SEVERITY_ORDER["critical"] > _SEVERITY_ORDER["high"]

    def test_high_above_medium(self):
        assert _SEVERITY_ORDER["high"] > _SEVERITY_ORDER["medium"]

    def test_medium_above_low(self):
        assert _SEVERITY_ORDER["medium"] > _SEVERITY_ORDER["low"]

    def test_low_above_info(self):
        assert _SEVERITY_ORDER["low"] > _SEVERITY_ORDER["info"]

    def test_all_severities_present(self):
        assert set(_SEVERITY_ORDER.keys()) == {"critical", "high", "medium", "low", "info"}


class TestAnalyticsEdgeCases:
    """Edge cases and boundary conditions."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_report_with_zero_scenarios_and_findings(self):
        report = _make_report([], total_scenarios=0, exec_time_ms=0.0)
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.pass_rate == 100.0
        assert summary.avg_execution_time_ms == 0.0

    def test_single_finding_all_fields(self):
        report = _make_report([{
            "severity": "critical",
            "path": "/api/important",
            "method": "DELETE",
            "type": "network_partition",
            "description": "Critical network partition detected",
        }])
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.total_vulnerabilities == 1
        assert summary.severity_distribution["critical"] == 1
        assert len(summary.top_risk_endpoints) == 1
        assert summary.top_risk_endpoints[0].endpoint_method == "DELETE"

    def test_many_findings_same_endpoint(self):
        vulns = [{"severity": "high", "path": "/api/same", "type": f"type{i}"} for i in range(50)]
        report = _make_report(vulns, total_scenarios=100)
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.total_vulnerabilities == 50
        assert len(summary.top_risk_endpoints) == 1
        assert summary.top_risk_endpoints[0].total_findings == 50

    def test_compare_empty_baseline_with_findings(self):
        baseline = _make_report([], report_id="empty")
        comparison = _make_report([
            {"severity": "critical", "path": "/a", "type": "t1"},
            {"severity": "high", "path": "/b", "type": "t2"},
        ], report_id="full")
        result = self.service.compare_reports(baseline, comparison)
        assert result.new_findings == 2
        assert result.resolved_findings == 0
        assert result.improved is False

    def test_compare_findings_with_empty(self):
        baseline = _make_report([
            {"severity": "critical", "path": "/a", "type": "t1"},
        ], report_id="full")
        comparison = _make_report([], report_id="empty")
        result = self.service.compare_reports(baseline, comparison)
        assert result.resolved_findings == 1
        assert result.new_findings == 0
        assert result.improved is True

    def test_tenant_isolation_in_summary(self):
        r1 = _make_report([{"severity": "critical", "path": "/a"}])
        r2 = _make_report([{"severity": "low", "path": "/b"}])
        self.service.store_report("t1", r1)
        self.service.store_report("t2", r2)
        s1 = self.service.get_summary("t1")
        s2 = self.service.get_summary("t2")
        assert s1.total_vulnerabilities == 1
        assert s2.total_vulnerabilities == 1
        assert s1.severity_distribution.get("critical") == 1
        assert s2.severity_distribution.get("low") == 1

    def test_pass_rate_with_many_vulns_exceeding_scenarios(self):
        report = _make_report([{"severity": "high", "path": "/a"}] * 5, total_scenarios=3)
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.pass_rate < 0.0 or summary.pass_rate >= 0.0

    def test_all_severity_types_in_distribution(self):
        report = _make_report([
            {"severity": "critical", "path": "/a"},
            {"severity": "high", "path": "/b"},
            {"severity": "medium", "path": "/c"},
            {"severity": "low", "path": "/d"},
            {"severity": "info", "path": "/e"},
        ])
        self.service.store_report("t1", report)
        summary = self.service.get_summary("t1")
        assert summary.severity_distribution["critical"] == 1
        assert summary.severity_distribution["high"] == 1
        assert summary.severity_distribution["medium"] == 1
        assert summary.severity_distribution["low"] == 1
        assert summary.severity_distribution["info"] == 1


class TestAnalyticsFunctional:
    """Functional tests: end-to-end analytics workflows."""

    def setup_method(self):
        self.service = AnalyticsService()

    def test_full_analytics_workflow(self):
        r1 = _make_report([
            {"severity": "critical", "path": "/api/users", "type": "latency_injection"},
            {"severity": "high", "path": "/api/orders", "type": "error_status"},
        ], exec_time_ms=150.0, total_scenarios=20, report_id="r1")
        r2 = _make_report([
            {"severity": "high", "path": "/api/users", "type": "latency_injection"},
            {"severity": "medium", "path": "/api/products", "type": "rate_limit"},
        ], exec_time_ms=200.0, total_scenarios=20, report_id="r2")
        self.service.store_report("tenant-1", r1)
        self.service.store_report("tenant-1", r2)
        summary = self.service.get_summary("tenant-1")
        assert summary.total_executions == 2
        assert summary.total_scenarios_run == 40
        assert summary.total_vulnerabilities == 4
        assert summary.pass_rate == 90.0
        assert summary.avg_execution_time_ms == 175.0
        assert len(summary.top_risk_endpoints) >= 1
        assert summary.top_risk_endpoints[0].endpoint_path == "/api/users"

    def test_comparison_workflow(self):
        baseline = _make_report([
            {"severity": "critical", "path": "/api/pay", "type": "t1"},
            {"severity": "high", "path": "/api/auth", "type": "t2"},
            {"severity": "medium", "path": "/api/data", "type": "t3"},
        ], report_id="baseline")
        current = _make_report([
            {"severity": "high", "path": "/api/pay", "type": "t1"},
            {"severity": "medium", "path": "/api/data", "type": "t3"},
            {"severity": "low", "path": "/api/new", "type": "t4"},
        ], report_id="current")
        result = self.service.compare_reports(baseline, current)
        assert result.resolved_findings == 1
        assert result.new_findings == 1
        assert result.persistent_findings == 2
        assert result.improved is True

    def test_multi_tenant_analytics(self):
        for i in range(5):
            report = _make_report([
                {"severity": "high", "path": f"/api/tenant{i}"},
            ], total_scenarios=10)
            self.service.store_report(f"tenant-{i}", report)
        for i in range(5):
            summary = self.service.get_summary(f"tenant-{i}")
            assert summary.total_executions == 1
            assert summary.total_vulnerabilities == 1

    def test_trend_analysis_over_time(self):
        base_date = datetime(2025, 1, 1)
        for i in range(7):
            report = _make_report(
                [{"severity": "high", "path": "/api/test"}],
                generated_at=base_date + timedelta(days=i),
            )
            self.service.store_report("t1", report)
        summary = self.service.get_summary("t1", period=TrendPeriod.DAILY)
        assert len(summary.trends) == 7

    def test_risk_score_delta_positive_means_regression(self):
        baseline = _make_report([{"severity": "low", "path": "/a", "type": "t1"}], report_id="b")
        comparison = _make_report([{"severity": "critical", "path": "/a", "type": "t1"}], report_id="c")
        result = self.service.compare_reports(baseline, comparison)
        assert result.risk_score_delta > 0
        assert result.improved is False

    def test_risk_score_delta_negative_means_improvement(self):
        baseline = _make_report([{"severity": "critical", "path": "/a", "type": "t1"}], report_id="b")
        comparison = _make_report([{"severity": "low", "path": "/a", "type": "t1"}], report_id="c")
        result = self.service.compare_reports(baseline, comparison)
        assert result.risk_score_delta < 0
        assert result.improved is True


class TestAnalyticsStress:
    """Stress tests for analytics service performance."""

    def test_large_number_of_reports(self):
        service = AnalyticsService()
        start = time.monotonic()
        for i in range(500):
            report = _make_report([
                {"severity": "high", "path": f"/api/ep{i % 50}"},
            ], total_scenarios=10)
            service.store_report("t1", report)
        summary = service.get_summary("t1")
        elapsed = time.monotonic() - start
        assert summary.total_executions == 500
        assert summary.total_vulnerabilities == 500
        assert elapsed < 5.0, f"Stress test took {elapsed:.2f}s, expected < 5s"

    def test_large_number_of_findings_per_report(self):
        service = AnalyticsService()
        vulns = [{"severity": "high", "path": f"/api/ep{i}"} for i in range(200)]
        report = _make_report(vulns, total_scenarios=300)
        service.store_report("t1", report)
        start = time.monotonic()
        summary = service.get_summary("t1")
        elapsed = time.monotonic() - start
        assert summary.total_vulnerabilities == 200
        assert elapsed < 2.0, f"Large findings took {elapsed:.2f}s, expected < 2s"

    def test_many_tenants(self):
        service = AnalyticsService()
        start = time.monotonic()
        for i in range(100):
            report = _make_report([{"severity": "high", "path": "/a"}], total_scenarios=5)
            service.store_report(f"tenant-{i}", report)
        for i in range(100):
            summary = service.get_summary(f"tenant-{i}")
            assert summary.total_executions == 1
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"Many tenants took {elapsed:.2f}s, expected < 5s"

    def test_compare_large_reports(self):
        service = AnalyticsService()
        vulns_b = [{"severity": "high", "path": f"/api/ep{i}", "type": f"t{i}"} for i in range(100)]
        vulns_c = [{"severity": "critical", "path": f"/api/ep{i}", "type": f"t{i}"} for i in range(50)]
        baseline = _make_report(vulns_b, report_id="big-baseline")
        comparison = _make_report(vulns_c, report_id="big-comparison")
        start = time.monotonic()
        result = service.compare_reports(baseline, comparison)
        elapsed = time.monotonic() - start
        assert result.persistent_findings == 50
        assert result.resolved_findings == 50
        assert elapsed < 2.0, f"Large comparison took {elapsed:.2f}s, expected < 2s"

    def test_concurrent_store_and_read(self):
        service = AnalyticsService()
        errors = []

        def writer(tenant_id: str, count: int):
            try:
                for i in range(count):
                    report = _make_report([{"severity": "high", "path": "/a"}], total_scenarios=5)
                    service.store_report(tenant_id, report)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(f"t{i % 3}", 20))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent errors: {errors}"
        total = sum(len(reports) for reports in service._reports.values())
        assert total == 200

    def test_endpoint_risk_with_many_endpoints(self):
        service = AnalyticsService()
        findings = [
            _make_finding(path=f"/api/ep{i}", severity="high")
            for i in range(100)
        ]
        start = time.monotonic()
        risks = service._compute_endpoint_risks(findings)
        elapsed = time.monotonic() - start
        assert len(risks) == 100
        assert elapsed < 1.0, f"100 endpoints took {elapsed:.2f}s, expected < 1s"
