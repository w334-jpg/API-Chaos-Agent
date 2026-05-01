"""Comprehensive unit tests for ReportGenerator service."""

from __future__ import annotations

from datetime import datetime

import pytest

from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    Report,
    ReportSummary,
    ResponseData,
    ScenarioResult,
    Severity,
    TestResult,
)
from api_chaos_agent.services.report_generator import ReportGenerator


@pytest.fixture
def config() -> ExecutionConfig:
    return ExecutionConfig(
        base_url="http://localhost:8000",
        concurrency=10,
        timeout_seconds=30,
        max_retries=1,
        headers={},
    )


def _make_scenario_result(
    scenario_type: str = "latency",
    vulnerability_found: bool = False,
    severity: Severity = Severity.MEDIUM,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id="test-id",
        scenario_name=f"Test {scenario_type}",
        scenario_type=scenario_type,
        severity=severity,
        status=status,
        response=ResponseData(status_code=200, body={"ok": True}, elapsed_ms=50.0),
        vulnerability_found=vulnerability_found,
        details="Test details",
    )


@pytest.fixture
def test_result_with_vulns(config) -> TestResult:
    results = [
        _make_scenario_result("latency", vulnerability_found=True, severity=Severity.HIGH),
        _make_scenario_result("error_status", vulnerability_found=True, severity=Severity.CRITICAL),
        _make_scenario_result(
            "request_tampering", vulnerability_found=False, severity=Severity.MEDIUM
        ),
        _make_scenario_result("rate_limit", vulnerability_found=True, severity=Severity.LOW),
    ]
    return TestResult(
        total_scenarios=4,
        completed_scenarios=3,
        failed_scenarios=1,
        config=config,
        results=results,
    )


@pytest.fixture
def test_result_no_vulns(config) -> TestResult:
    results = [
        _make_scenario_result("latency", vulnerability_found=False),
        _make_scenario_result("error_status", vulnerability_found=False),
    ]
    return TestResult(
        total_scenarios=2,
        completed_scenarios=2,
        failed_scenarios=0,
        config=config,
        results=results,
    )


@pytest.fixture
def generator() -> ReportGenerator:
    return ReportGenerator()


class TestGenerateReport:
    def test_generate_returns_report(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert isinstance(report, Report)

    def test_report_has_id(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.id
        assert isinstance(report.id, str)

    def test_report_has_created_at(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert isinstance(report.created_at, datetime)

    def test_report_total_scenarios(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.summary.total_scenarios == 4

    def test_report_vulnerabilities_count(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.summary.failed == 3

    def test_report_no_vulnerabilities(self, generator, test_result_no_vulns):
        report = generator.generate(test_result_no_vulns)
        assert report.summary.failed == 0

    def test_report_includes_test_result(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.test_result == test_result_with_vulns


class TestExtractFindings:
    def test_extracts_vulnerable_findings(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        assert len(findings) == 3
        for f in findings:
            assert f.vulnerability_found is True

    def test_no_findings_when_no_vulns(self, generator, test_result_no_vulns):
        findings = generator._extract_findings(test_result_no_vulns)
        assert len(findings) == 0

    def test_findings_sorted_by_severity(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        for i in range(len(findings) - 1):
            assert severity_order.get(findings[i].severity.value, 99) <= severity_order.get(
                findings[i + 1].severity.value, 99
            )

    def test_finding_has_recommendation(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        for f in findings:
            assert f.recommendation
            assert isinstance(f.recommendation, str)


class TestSeveritySummary:
    def test_summary_in_report(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert isinstance(report.summary, ReportSummary)
        assert report.summary.severity_counts is not None

    def test_empty_summary_for_no_findings(self, generator, test_result_no_vulns):
        report = generator.generate(test_result_no_vulns)
        assert report.summary.severity_counts == {}


class TestRemediation:
    def test_latency_remediation(self, generator):
        result = _make_scenario_result("latency", vulnerability_found=True)
        remediation = generator._suggest_remediation(result)
        assert "timeout" in remediation.lower() or "circuit" in remediation.lower()

    def test_error_status_remediation(self, generator):
        result = _make_scenario_result("error_status", vulnerability_found=True)
        remediation = generator._suggest_remediation(result)
        assert "error" in remediation.lower() or "graceful" in remediation.lower()

    def test_tampering_remediation(self, generator):
        result = _make_scenario_result("request_tampering", vulnerability_found=True)
        remediation = generator._suggest_remediation(result)
        assert "validation" in remediation.lower() or "sanitization" in remediation.lower()

    def test_rate_limit_remediation(self, generator):
        result = _make_scenario_result("rate_limit", vulnerability_found=True)
        remediation = generator._suggest_remediation(result)
        assert "rate" in remediation.lower()

    def test_unknown_type_remediation(self, generator):
        result = _make_scenario_result("unknown_type", vulnerability_found=True)
        remediation = generator._suggest_remediation(result)
        assert isinstance(remediation, str)
        assert len(remediation) > 0
