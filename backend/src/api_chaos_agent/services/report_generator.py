"""Report Generator — generates structured reports from test results."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api_chaos_agent.models.report import (
    Finding,
    Report,
    ScenarioResult,
    Severity,
    TestResult,
)
from api_chaos_agent.models.scenario import ChaosScenarioType


_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


class ReportGenerator:
    """Generate structured reports from chaos test results."""

    def generate(self, test_result: TestResult) -> Report:
        findings = self._extract_findings(test_result)
        severity_summary = self._summarize_severities(findings)

        return Report(
            title=f"API Chaos Test Report — {test_result.started_at.isoformat()}",
            generated_at=datetime.now(),
            total_scenarios=test_result.total_scenarios,
            vulnerabilities_found=sum(1 for f in findings if f.vulnerability_found),
            severity_summary=severity_summary,
            findings=findings,
            test_result=test_result,
        )

    def _extract_findings(self, test_result: TestResult) -> list[Finding]:
        findings: list[Finding] = []

        for result in test_result.results:
            if result.vulnerability_found:
                finding = Finding(
                    scenario_id=result.scenario_id,
                    scenario_name=result.scenario_name,
                    scenario_type=result.scenario_type,
                    endpoint_path="",
                    endpoint_method="",
                    severity=result.severity,
                    vulnerability_found=True,
                    description=result.details or f"Vulnerability found in {result.scenario_name}",
                    reproduction_steps=self._build_reproduction_steps(result),
                    remediation=self._suggest_remediation(result),
                    response_snapshot=self._snapshot_response(result),
                )
                findings.append(finding)

        return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 99))

    def _summarize_severities(self, findings: list[Finding]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for finding in findings:
            key = finding.severity.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _build_reproduction_steps(self, result: ScenarioResult) -> list[str]:
        steps = [f"Execute scenario: {result.scenario_name}"]
        if result.response.status_code:
            steps.append(f"Observe status code: {result.response.status_code}")
        if result.response.error:
            steps.append(f"Observe error: {result.response.error}")
        return steps

    def _suggest_remediation(self, result: ScenarioResult) -> str:
        try:
            st = ChaosScenarioType(result.scenario_type)
        except ValueError:
            return "Review and fix the identified issue."

        if st == ChaosScenarioType.LATENCY:
            return "Implement proper timeout handling and circuit breakers for slow responses."
        if st == ChaosScenarioType.ERROR_STATUS:
            return "Implement proper error handling and ensure graceful degradation."
        if st == ChaosScenarioType.REQUEST_TAMPERING:
            return "Add input validation and sanitization for all request fields."
        if st == ChaosScenarioType.RATE_LIMIT:
            return "Implement rate limiting to prevent abuse and ensure fair resource allocation."
        return "Review and fix the identified issue."

    def _snapshot_response(self, result: ScenarioResult) -> dict[str, Any]:
        snap: dict[str, Any] = {}
        if result.response.status_code is not None:
            snap["status_code"] = result.response.status_code
        if result.response.elapsed_ms:
            snap["elapsed_ms"] = result.response.elapsed_ms
        if result.response.error:
            snap["error"] = result.response.error
        if result.response.body is not None:
            body = result.response.body
            if isinstance(body, (dict, list)):
                snap["body_preview"] = str(body)[:500]
            elif isinstance(body, str):
                snap["body_preview"] = body[:500]
        return snap
