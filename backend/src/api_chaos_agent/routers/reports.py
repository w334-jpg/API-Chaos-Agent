"""Reports router — generate and retrieve test reports."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.report import Report
from api_chaos_agent.services.report_generator import ReportGenerator
from api_chaos_agent.services.store import store

router = APIRouter(prefix="/api/reports", tags=["reports"])

_MAX_ID_LEN = 256
_ALLOWED_FORMATS: set[str] = {"json", "html"}


@router.post("/generate/{execution_id}", response_model=dict)
async def generate_report(
    execution_id: str,
    _user: CurrentUser,
    format: str = "json",
) -> dict:
    if len(execution_id) > _MAX_ID_LEN:
        raise HTTPException(status_code=400, detail="execution_id too long")

    if format not in _ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Invalid format '{format}'. Allowed: {', '.join(sorted(_ALLOWED_FORMATS))}")

    test_result = await store.get_execution(execution_id)
    if test_result is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    generator = ReportGenerator()
    report = generator.generate(test_result)

    report_id = await store.save_report(report)

    if format == "html":
        html_content = _render_html_report(report)
        return {"report_id": report_id, "format": "html", "html": html_content}

    return {
        "report_id": report_id,
        "format": "json",
        "title": report.title,
        "total_scenarios": report.total_scenarios,
        "vulnerabilities_found": report.vulnerabilities_found,
        "severity_summary": report.severity_summary,
        "findings_count": len(report.findings),
    }


@router.get("/", response_model=dict)
async def list_reports(_user: CurrentUser) -> dict:
    reports = await store.list_reports()
    return {
        "reports": [
            {
                "id": rid,
                "title": r.title,
                "generated_at": str(r.generated_at),
                "vulnerabilities_found": r.vulnerabilities_found,
            }
            for rid, r in reports.items()
        ]
    }


@router.get("/{report_id}", response_model=Report)
async def get_report(report_id: str, _user: CurrentUser) -> Report:
    if len(report_id) > _MAX_ID_LEN:
        raise HTTPException(status_code=400, detail="report_id too long")
    report = await store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _render_html_report(report: Report) -> str:
    findings_rows = ""
    for f in report.findings:
        findings_rows += f"""
        <tr>
            <td>{f.scenario_name}</td>
            <td>{f.scenario_type}</td>
            <td>{f.severity.value}</td>
            <td>{'Yes' if f.vulnerability_found else 'No'}</td>
            <td>{f.description[:100]}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><title>{report.title}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #4CAF50; color: white; }}
tr:nth-child(even) {{ background-color: #f2f2f2; }}
</style></head><body>
<h1>{report.title}</h1>
<p>Generated: {report.generated_at}</p>
<p>Total Scenarios: {report.total_scenarios}</p>
<p>Vulnerabilities Found: {report.vulnerabilities_found}</p>
<h2>Severity Summary</h2>
<pre>{report.severity_summary}</pre>
<h2>Findings</h2>
<table><tr><th>Scenario</th><th>Type</th><th>Severity</th><th>Vulnerable</th><th>Description</th></tr>
{findings_rows}</table></body></html>"""
