"""Report Generator — generates structured reports from test results."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from api_chaos_agent.models.report import (
    Finding,
    Report,
    ReportSummary,
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

    def generate(self, test_result: TestResult, schema_id: str = "", tenant_id: str = "") -> Report:
        findings = self._extract_findings(test_result)
        summary = self._build_summary(test_result, findings)

        return Report(
            id=str(uuid.uuid4()),
            schema_id=schema_id,
            created_at=datetime.now(),
            summary=summary,
            findings=findings,
            test_result=test_result,
            tenant_id=tenant_id,
        )

    def _build_summary(self, test_result: TestResult, findings: list[Finding]) -> ReportSummary:
        severity_counts: dict[str, int] = {}
        for f in findings:
            key = f.severity.value
            severity_counts[key] = severity_counts.get(key, 0) + 1

        total = test_result.total_scenarios or len(test_result.results)
        passed = sum(1 for r in test_result.results if not r.vulnerability_found)
        failed = sum(1 for r in test_result.results if r.vulnerability_found)
        errors = sum(1 for r in test_result.results if r.status.value == "failed")
        vuln_rate = (failed / total * 100) if total > 0 else 0.0

        return ReportSummary(
            total_endpoints=0,
            total_scenarios=total,
            passed=passed,
            failed=failed,
            errors=errors,
            severity_counts=severity_counts,
            vulnerability_rate=round(vuln_rate, 2),
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
                    details=result.details or f"Vulnerability found in {result.scenario_name}",
                    recommendation=self._suggest_remediation(result),
                    response_status=result.response.status_code,
                    expected_behavior="",
                    actual_behavior=result.response.error or "",
                )
                findings.append(finding)

        return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 99))

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
