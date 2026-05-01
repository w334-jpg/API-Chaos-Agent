"""Report export module - Export test reports in HTML, JSON, and CSV formats.

Provides structured export capabilities for test results, supporting:
- HTML: Interactive visual report with charts and tables
- JSON: Machine-readable structured data
- CSV: Spreadsheet-compatible tabular data
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from api_chaos_agent.models.report import Finding, Report, ScenarioResult


class ReportExporter:
    """Export test reports in multiple formats."""

    def export_html(self, report: Report) -> str:
        title = "API Chaos Test Report"
        generated = (
            report.created_at.isoformat()
            if report.created_at
            else datetime.now(UTC).isoformat()
        )

        vuln_rows = ""
        for v in report.findings:
            severity_class = (
                f"severity-{v.severity.value}"
                if hasattr(v.severity, "value")
                else "severity-medium"
            )
            vuln_rows += f"""
            <tr class="{severity_class}">
                <td>{_esc(v.scenario_id)}</td>
                <td>{_esc(v.scenario_type)}</td>
                <td><span class="badge {severity_class}">{_esc(str(v.severity))}</span></td>
                <td>{_esc(v.details)}</td>
                <td>{_esc(v.recommendation or "")}</td>
            </tr>"""

        scenario_rows = ""
        for s in self._get_scenario_results(report):
            status_val = str(s.status.value) if hasattr(s.status, "value") else str(s.status)
            status_class = "status-passed" if status_val == "completed" else "status-failed"
            duration_str = f"{s.response.elapsed_ms:.0f}ms" if s.response.elapsed_ms else "N/A"
            error_str = s.response.error or s.details or ""
            scenario_rows += f"""
            <tr class="{status_class}">
                <td>{_esc(s.scenario_id)}</td>
                <td>{_esc(s.scenario_type)}</td>
                <td><span class="badge {status_class}">{_esc(status_val)}</span></td>
                <td>{_esc(duration_str)}</td>
                <td>{_esc(error_str)}</td>
            </tr>"""

        summary = report.summary
        severity_summary = summary.severity_counts
        total_scenarios = summary.total_scenarios
        completed = summary.passed
        failed = summary.failed
        vuln_count = len(report.findings)
        pass_rate = (completed / total_scenarios * 100) if total_scenarios > 0 else 0

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>
:root {{ --primary: #2563eb; --danger: #dc2626; --warning: #f59e0b; --success: #16a34a; --gray: #6b7280; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
h1 {{ font-size: 1.875rem; font-weight: 700; margin-bottom: 0.5rem; }}
.subtitle {{ color: var(--gray); margin-bottom: 2rem; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
.card {{ background: white; border-radius: 0.75rem; padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.card h3 {{ font-size: 0.875rem; color: var(--gray); text-transform: uppercase; letter-spacing: 0.05em; }}
.card .value {{ font-size: 2rem; font-weight: 700; margin-top: 0.25rem; }}
.card .value.success {{ color: var(--success); }}
.card .value.danger {{ color: var(--danger); }}
.card .value.warning {{ color: var(--warning); }}
.card .value.primary {{ color: var(--primary); }}
section {{ background: white; border-radius: 0.75rem; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
section h2 {{ font-size: 1.25rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e2e8f0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
th {{ text-align: left; padding: 0.75rem 1rem; background: #f1f5f9; font-weight: 600; color: var(--gray); }}
td {{ padding: 0.75rem 1rem; border-bottom: 1px solid #f1f5f9; }}
tr:hover {{ background: #f8fafc; }}
.badge {{ display: inline-block; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }}
.severity-critical, .status-failed {{ background: #fef2f2; color: var(--danger); }}
.severity-high {{ background: #fff7ed; color: #ea580c; }}
.severity-medium {{ background: #fffbeb; color: var(--warning); }}
.severity-low {{ background: #f0fdf4; color: var(--success); }}
.status-passed {{ background: #f0fdf4; color: var(--success); }}
footer {{ text-align: center; color: var(--gray); font-size: 0.875rem; margin-top: 2rem; }}
</style>
</head>
<body>
<div class="container">
<h1>{_esc(title)}</h1>
<p class="subtitle">Generated: {_esc(generated)}</p>

<div class="cards">
  <div class="card"><h3>Total Scenarios</h3><div class="value primary">{total_scenarios}</div></div>
  <div class="card"><h3>Passed</h3><div class="value success">{completed}</div></div>
  <div class="card"><h3>Failed</h3><div class="value danger">{failed}</div></div>
  <div class="card"><h3>Pass Rate</h3><div class="value {"success" if pass_rate >= 80 else "warning" if pass_rate >= 50 else "danger"}">{pass_rate:.1f}%</div></div>
  <div class="card"><h3>Vulnerabilities</h3><div class="value {"danger" if vuln_count > 0 else "success"}">{vuln_count}</div></div>
</div>

<section>
<h2>Severity Distribution</h2>
<table>
<tr><th>Critical</th><th>High</th><th>Medium</th><th>Low</th><th>Info</th></tr>
<tr>
  <td><span class="badge severity-critical">{severity_summary.get("critical", 0)}</span></td>
  <td><span class="badge severity-high">{severity_summary.get("high", 0)}</span></td>
  <td><span class="badge severity-medium">{severity_summary.get("medium", 0)}</span></td>
  <td><span class="badge severity-low">{severity_summary.get("low", 0)}</span></td>
  <td><span class="badge">{severity_summary.get("info", 0)}</span></td>
</tr>
</table>
</section>

<section>
<h2>Vulnerabilities Found</h2>
{"<table><tr><th>Scenario</th><th>Type</th><th>Severity</th><th>Details</th><th>Recommendation</th></tr>" + vuln_rows + "</table>" if vuln_rows else "<p>No vulnerabilities found.</p>"}
</section>

<section>
<h2>Scenario Results</h2>
<table>
<tr><th>Scenario ID</th><th>Type</th><th>Status</th><th>Duration</th><th>Error</th></tr>
{scenario_rows}
</table>
</section>

<footer>API Chaos Agent Report &mdash; {_esc(generated)}</footer>
</div>
</body>
</html>"""

    def export_json(self, report: Report) -> str:
        data = self._report_to_dict(report)
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    def export_csv(self, report: Report) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "scenario_id",
                "scenario_type",
                "status",
                "duration_ms",
                "status_code",
                "error_message",
                "is_vulnerability",
                "severity",
                "details",
                "recommendation",
            ]
        )

        vuln_map: dict[str, Finding] = {}
        for v in report.findings:
            vuln_map[v.scenario_id] = v

        for s in self._get_scenario_results(report):
            vuln = vuln_map.get(s.scenario_id)
            status_val = str(s.status.value) if hasattr(s.status, "value") else str(s.status)
            writer.writerow(
                [
                    s.scenario_id,
                    s.scenario_type,
                    status_val,
                    f"{s.response.elapsed_ms:.0f}" if s.response.elapsed_ms else "",
                    s.response.status_code or "",
                    s.response.error or s.details or "",
                    "yes" if vuln else "no",
                    str(vuln.severity) if vuln else "",
                    vuln.details if vuln else "",
                    vuln.recommendation if vuln else "",
                ]
            )

        return output.getvalue()

    def _get_scenario_results(self, report: Report) -> list[ScenarioResult]:
        if report.test_result and report.test_result.results:
            return report.test_result.results
        return []

    def _report_to_dict(self, report: Report) -> dict[str, Any]:
        return {
            "id": report.id,
            "schema_id": report.schema_id,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "summary": report.summary.model_dump(),
            "findings": [
                {
                    "scenario_id": v.scenario_id,
                    "scenario_type": v.scenario_type,
                    "severity": str(v.severity),
                    "details": v.details,
                    "recommendation": v.recommendation,
                }
                for v in report.findings
            ],
            "scenario_results": [
                {
                    "scenario_id": s.scenario_id,
                    "scenario_type": s.scenario_type,
                    "status": str(s.status.value) if hasattr(s.status, "value") else str(s.status),
                    "duration_ms": s.response.elapsed_ms,
                    "status_code": s.response.status_code,
                    "error_message": s.response.error or s.details or "",
                }
                for s in self._get_scenario_results(report)
            ],
        }


def _esc(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
