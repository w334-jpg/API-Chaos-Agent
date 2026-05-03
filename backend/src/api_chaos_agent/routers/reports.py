"""Reports router — generate and retrieve test reports."""

from __future__ import annotations

import html as html_module
from typing import Any

from fastapi import APIRouter

from api_chaos_agent.core.deps import StoreDep
from api_chaos_agent.core.exceptions import NotFoundError, RequestError
from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.report import Report
from api_chaos_agent.services.report_generator import ReportGenerator

router = APIRouter(prefix="/api/reports", tags=["reports"])

_MAX_ID_LEN = 256
_ALLOWED_FORMATS: set[str] = {"json", "html"}


def _esc(value: object) -> str:
    return html_module.escape(str(value))


@router.post("/generate/{execution_id}", response_model=dict)
async def generate_report(
    execution_id: str,
    _user: CurrentUser,
    store: StoreDep,
    format: str = "json",
) -> dict[str, Any]:
    if len(execution_id) > _MAX_ID_LEN:
        raise RequestError(detail="execution_id too long")

    if format not in _ALLOWED_FORMATS:
        raise RequestError(
            detail=f"Invalid format '{format}'. Allowed: {', '.join(sorted(_ALLOWED_FORMATS))}"
        )

    test_result = await store.get_execution(execution_id)
    if test_result is None:
        raise NotFoundError(detail="Execution not found")

    generator = ReportGenerator()
    report = generator.generate(test_result)

    report_id = await store.save_report(report)

    if format == "html":
        html_content = _render_html_report(report)
        return {"report_id": report_id, "format": "html", "html": html_content}

    return {
        "report_id": report_id,
        "format": "json",
        "id": report.id,
        "schema_id": report.schema_id,
        "summary": report.summary.model_dump(),
        "findings_count": len(report.findings),
    }


@router.get("/", response_model=dict)
async def list_reports(_user: CurrentUser, store: StoreDep) -> dict[str, Any]:
    reports = await store.list_reports()
    return {
        "reports": [
            {
                "id": rid,
                "schema_id": r.schema_id,
                "created_at": str(r.created_at),
                "summary": r.summary.model_dump(),
            }
            for rid, r in reports.items()
        ]
    }


@router.get("/{report_id}", response_model=Report)
async def get_report(report_id: str, _user: CurrentUser, store: StoreDep) -> Report:
    if len(report_id) > _MAX_ID_LEN:
        raise RequestError(detail="report_id too long")
    report = await store.get_report(report_id)
    if report is None:
        raise NotFoundError(detail="Report not found")
    return report


def _render_html_report(report: Report) -> str:
    findings_rows = ""
    for f in report.findings:
        findings_rows += f"""
        <tr>
            <td>{_esc(f.scenario_name)}</td>
            <td>{_esc(f.scenario_type)}</td>
            <td>{_esc(f.severity.value)}</td>
            <td>{"Yes" if f.vulnerability_found else "No"}</td>
            <td>{_esc(f.details[:100])}</td>
        </tr>"""

    summary = report.summary
    return f"""<!DOCTYPE html>
<html><head><title>Chaos Test Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #4CAF50; color: white; }}
tr:nth-child(even) {{ background-color: #f2f2f2; }}
</style></head><body>
<h1>API Chaos Test Report</h1>
<p>Created: {_esc(report.created_at)}</p>
<p>Total Scenarios: {_esc(summary.total_scenarios)}</p>
<p>Passed: {_esc(summary.passed)} | Failed: {_esc(summary.failed)} | Errors: {_esc(summary.errors)}</p>
<p>Vulnerability Rate: {_esc(summary.vulnerability_rate)}%</p>
<h2>Findings</h2>
<table><tr><th>Scenario</th><th>Type</th><th>Severity</th><th>Vulnerable</th><th>Details</th></tr>
{findings_rows}</table></body></html>"""
