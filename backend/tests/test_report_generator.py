"""Comprehensive unit tests for ReportGenerator service."""

from __future__ import annotations

from datetime import datetime

import pytest

from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    Finding,
    Report,
    ResponseData,
    ScenarioResult,
    Severity,
    TestResult,
)
from api_chaos_agent.models.scenario import ChaosScenarioType
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
        _make_scenario_result("request_tampering", vulnerability_found=False, severity=Severity.MEDIUM),
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

    def test_report_has_title(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.title
        assert "API Chaos Test Report" in report.title

    def test_report_has_generated_at(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert isinstance(report.generated_at, datetime)

    def test_report_total_scenarios(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.total_scenarios == 4

    def test_report_vulnerabilities_count(self, generator, test_result_with_vulns):
        report = generator.generate(test_result_with_vulns)
        assert report.vulnerabilities_found == 3

    def test_report_no_vulnerabilities(self, generator, test_result_no_vulns):
        report = generator.generate(test_result_no_vulns)
        assert report.vulnerabilities_found == 0

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
            assert severity_order.get(findings[i].severity.value, 99) <= severity_order.get(findings[i + 1].severity.value, 99)

    def test_finding_has_remediation(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        for f in findings:
            assert f.remediation
            assert isinstance(f.remediation, str)

    def test_finding_has_reproduction_steps(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        for f in findings:
            assert isinstance(f.reproduction_steps, list)
            assert len(f.reproduction_steps) > 0

    def test_finding_has_response_snapshot(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        for f in findings:
            assert isinstance(f.response_snapshot, dict)


class TestSeveritySummary:

    def test_summary_counts(self, generator, test_result_with_vulns):
        findings = generator._extract_findings(test_result_with_vulns)
        summary = generator._summarize_severities(findings)
        assert isinstance(summary, dict)
        total = sum(summary.values())
        assert total == len(findings)

    def test_empty_summary_for_no_findings(self, generator, test_result_no_vulns):
        findings = generator._extract_findings(test_result_no_vulns)
        summary = generator._summarize_severities(findings)
        assert summary == {}


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


class TestResponseSnapshot:

    def test_snapshot_includes_status_code(self, generator):
        result = _make_scenario_result()
        snap = generator._snapshot_response(result)
        assert "status_code" in snap
        assert snap["status_code"] == 200

    def test_snapshot_includes_elapsed(self, generator):
        result = _make_scenario_result()
        snap = generator._snapshot_response(result)
        assert "elapsed_ms" in snap

    def test_snapshot_includes_error(self, generator):
        result = ScenarioResult(
            scenario_id="test",
            scenario_name="test",
            scenario_type="latency",
            severity=Severity.MEDIUM,
            status=ExecutionStatus.FAILED,
            response=ResponseData(error="Connection refused"),
        )
        snap = generator._snapshot_response(result)
        assert "error" in snap

    def test_snapshot_includes_body_preview(self, generator):
        result = _make_scenario_result()
        snap = generator._snapshot_response(result)
        assert "body_preview" in snap


class TestReproductionSteps:

    def test_steps_include_scenario_name(self, generator):
        result = _make_scenario_result()
        steps = generator._build_reproduction_steps(result)
        assert any("latency" in s.lower() for s in steps)

    def test_steps_include_status_code(self, generator):
        result = _make_scenario_result()
        steps = generator._build_reproduction_steps(result)
        assert any("200" in s for s in steps)

    def test_steps_include_error(self, generator):
        result = ScenarioResult(
            scenario_id="test",
            scenario_name="test",
            scenario_type="latency",
            severity=Severity.MEDIUM,
            status=ExecutionStatus.FAILED,
            response=ResponseData(error="Timeout"),
        )
        steps = generator._build_reproduction_steps(result)
        assert any("Timeout" in s for s in steps)
