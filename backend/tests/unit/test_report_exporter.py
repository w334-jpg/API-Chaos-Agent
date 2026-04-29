"""Unit tests for ReportExporter."""

from __future__ import annotations

import json

import pytest

from api_chaos_agent.models.report import (
    ExecutionStatus,
    Finding,
    Report,
    ScenarioResult,
    TestResult,
)
from api_chaos_agent.models.scenario import Severity
from api_chaos_agent.services.report_exporter import ReportExporter


@pytest.fixture
def sample_report():
    result = TestResult(total_scenarios=3)
    result.results = [
        ScenarioResult(scenario_id="s1", scenario_name="SQL Injection", scenario_type="request_tampering",
                       status=ExecutionStatus.COMPLETED, severity=Severity.CRITICAL, vulnerability_found=True),
        ScenarioResult(scenario_id="s2", scenario_name="Rate Limit Bypass", scenario_type="rate_limit",
                       status=ExecutionStatus.COMPLETED, severity=Severity.HIGH, vulnerability_found=True),
        ScenarioResult(scenario_id="s3", scenario_name="Latency Test", scenario_type="latency",
                       status=ExecutionStatus.COMPLETED, severity=Severity.LOW, vulnerability_found=False),
    ]
    result.completed_scenarios = 3

    report = Report(
        title="Test Report",
        total_scenarios=3,
        vulnerabilities_found=2,
        severity_summary={"critical": 1, "high": 1, "medium": 0, "low": 0},
        findings=[
            Finding(
                scenario_id="s1", scenario_name="SQL Injection", scenario_type="request_tampering",
                endpoint_path="/users", endpoint_method="POST", severity=Severity.CRITICAL,
                vulnerability_found=True, description="SQL injection vulnerability detected",
                reproduction_steps=["Send POST with SQL payload", "Observe unfiltered response"],
                remediation="Use parameterized queries",
            ),
            Finding(
                scenario_id="s2", scenario_name="Rate Limit Bypass", scenario_type="rate_limit",
                endpoint_path="/api/data", endpoint_method="GET", severity=Severity.HIGH,
                vulnerability_found=True, description="Rate limiting not enforced",
                reproduction_steps=["Send 1000 requests rapidly", "Observe no 429 response"],
                remediation="Implement proper rate limiting middleware",
            ),
        ],
        test_result=result,
    )
    return report


class TestReportExporterHTML:
    def test_export_html_basic(self, sample_report):
        exporter = ReportExporter()
        html = exporter.export_html(sample_report)
        assert "<!DOCTYPE html>" in html
        assert "Test Report" in html
        assert len(html) > 100

    def test_export_html_contains_findings(self, sample_report):
        exporter = ReportExporter()
        html = exporter.export_html(sample_report)
        assert "sql injection" in html.lower()

    def test_export_html_contains_severity(self, sample_report):
        exporter = ReportExporter()
        html = exporter.export_html(sample_report)
        assert "critical" in html.lower() or "CRITICAL" in html

    def test_export_html_contains_stats(self, sample_report):
        exporter = ReportExporter()
        html = exporter.export_html(sample_report)
        assert "3" in html


class TestReportExporterJSON:
    def test_export_json_basic(self, sample_report):
        exporter = ReportExporter()
        json_str = exporter.export_json(sample_report)
        data = json.loads(json_str)
        assert "findings" in data
        assert data["total_scenarios"] == 3

    def test_export_json_findings(self, sample_report):
        exporter = ReportExporter()
        json_str = exporter.export_json(sample_report)
        data = json.loads(json_str)
        assert len(data["findings"]) == 2
        assert data["findings"][0]["severity"] == "Severity.CRITICAL"

    def test_export_json_valid(self, sample_report):
        exporter = ReportExporter()
        json_str = exporter.export_json(sample_report)
        json.loads(json_str)


class TestReportExporterCSV:
    def test_export_csv_basic(self, sample_report):
        exporter = ReportExporter()
        csv_str = exporter.export_csv(sample_report)
        assert "scenario_id" in csv_str
        assert len(csv_str) > 50

    def test_export_csv_contains_data(self, sample_report):
        exporter = ReportExporter()
        csv_str = exporter.export_csv(sample_report)
        assert "s1" in csv_str
        assert "s2" in csv_str

    def test_export_csv_vulnerability_flag(self, sample_report):
        exporter = ReportExporter()
        csv_str = exporter.export_csv(sample_report)
        assert "yes" in csv_str


class TestReportExporterEmpty:
    def test_export_html_no_findings(self):
        report = Report(title="Empty Report", total_scenarios=0, vulnerabilities_found=0, findings=[])
        exporter = ReportExporter()
        html = exporter.export_html(report)
        assert "<!DOCTYPE html>" in html
        assert "No vulnerabilities found" in html

    def test_export_json_empty(self):
        report = Report(title="Empty", total_scenarios=0, vulnerabilities_found=0, findings=[])
        exporter = ReportExporter()
        json_str = exporter.export_json(report)
        data = json.loads(json_str)
        assert data["findings"] == []

    def test_export_csv_empty(self):
        report = Report(title="Empty", total_scenarios=0, vulnerabilities_found=0, findings=[])
        exporter = ReportExporter()
        csv_str = exporter.export_csv(report)
        assert "scenario_id" in csv_str
