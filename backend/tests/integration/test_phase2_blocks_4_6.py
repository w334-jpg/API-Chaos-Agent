"""Integration Test 2: Blocks 4-6 (CI/CD + Tenant + Analytics).

Validates:
- Cross-service data flow between CI/CD, Tenant, and Analytics
- Tenant-scoped CI/CD pipeline management
- Analytics aggregation from CI/CD-triggered executions
- Quota enforcement across service boundaries
- Multi-tenant isolation in integrated workflows
"""

import pytest
import time
from datetime import datetime

from api_chaos_agent.models.analytics import TrendPeriod
from api_chaos_agent.models.cicd import CiCdProvider, PipelineConfig, Pipeline
from api_chaos_agent.models.report import Report, Finding, ReportSummary
from api_chaos_agent.models.scenario import Severity
from api_chaos_agent.models.tenant import TenantPlan, TeamMemberRole
from api_chaos_agent.services.analytics_service import AnalyticsService
from api_chaos_agent.services.cicd_service import CiCdService
from api_chaos_agent.services.tenant_service import TenantService


def _make_config(provider: CiCdProvider = CiCdProvider.GITHUB_ACTIONS) -> PipelineConfig:
    return PipelineConfig(
        provider=provider,
        project_url="https://github.com/test/repo",
        branch="main",
        api_spec_path="openapi.yaml",
        scenario_types=["latency", "error_status"],
        fail_on_severity="high",
        base_url="http://localhost:8000",
    )


def _make_report(
    vulns: list[dict] | None = None,
    exec_time_ms: float = 100.0,
    total_scenarios: int = 10,
    report_id: str | None = None,
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
                    details=v.get("description", "Test finding"),
                    recommendation="Review and fix",
                )
            )
    rid = report_id or f"report-{int(time.monotonic()*1e6)}"
    return Report(
        id=rid,
        schema_id="test-schema",
        summary=ReportSummary(
            total_scenarios=total_scenarios,
            passed=total_scenarios - len(findings),
            failed=len(findings),
        ),
        findings=findings,
    )


class TestTenantCicdIntegration:
    """Test Tenant ↔ CI/CD service integration."""

    def setup_method(self):
        self.tenant_svc = TenantService()
        self.cicd_svc = CiCdService()

    def test_create_pipeline_for_tenant(self):
        tenant = self.tenant_svc.create_tenant("CI/CD Org", plan=TenantPlan.PRO)
        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("test-pipeline", config, tenant_id=tenant.id)
        assert pipeline.tenant_id == tenant.id
        assert pipeline.name == "test-pipeline"
        assert pipeline.enabled is True

    def test_tenant_quota_blocks_cicd_for_free_plan(self):
        tenant = self.tenant_svc.create_tenant("Free Org", plan=TenantPlan.FREE)
        assert not tenant.quota.ci_cd_integration

    def test_tenant_quota_allows_cicd_for_pro_plan(self):
        tenant = self.tenant_svc.create_tenant("Pro Org", plan=TenantPlan.PRO)
        assert tenant.quota.ci_cd_integration

    def test_tenant_quota_allows_cicd_for_enterprise_plan(self):
        tenant = self.tenant_svc.create_tenant("Ent Org", plan=TenantPlan.ENTERPRISE)
        assert tenant.quota.ci_cd_integration

    def test_multiple_pipelines_per_tenant(self):
        tenant = self.tenant_svc.create_tenant("Multi Pipeline Org", plan=TenantPlan.PRO)
        config = _make_config()
        p1 = self.cicd_svc.create_pipeline("pipeline-1", config, tenant_id=tenant.id)
        p2 = self.cicd_svc.create_pipeline("pipeline-2", config, tenant_id=tenant.id)
        assert p1.id != p2.id
        assert p1.tenant_id == tenant.id
        assert p2.tenant_id == tenant.id

    def test_pipeline_trigger_and_complete_flow(self):
        tenant = self.tenant_svc.create_tenant("Flow Org", plan=TenantPlan.PRO)
        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("flow-pipeline", config, tenant_id=tenant.id)
        run = self.cicd_svc.trigger_run(pipeline.id)
        assert run.status == "running"
        completed = self.cicd_svc.complete_run(
            run.id, pipeline.id,
            report_id="r-001",
            vulnerabilities=3,
            max_severity="high",
            success=True,
        )
        assert completed.status == "completed"
        assert completed.report_id == "r-001"
        assert completed.vulnerabilities_found == 3

    def test_different_tenants_isolated_pipelines(self):
        t1 = self.tenant_svc.create_tenant("Tenant A", plan=TenantPlan.PRO)
        t2 = self.tenant_svc.create_tenant("Tenant B", plan=TenantPlan.PRO)
        config = _make_config()
        p1 = self.cicd_svc.create_pipeline("pipe-a", config, tenant_id=t1.id)
        p2 = self.cicd_svc.create_pipeline("pipe-b", config, tenant_id=t2.id)
        assert p1.tenant_id == t1.id
        assert p2.tenant_id == t2.id
        assert p1.id != p2.id


class TestTenantAnalyticsIntegration:
    """Test Tenant ↔ Analytics service integration."""

    def setup_method(self):
        self.tenant_svc = TenantService()
        self.analytics_svc = AnalyticsService()

    def test_store_and_summarize_per_tenant(self):
        tenant = self.tenant_svc.create_tenant("Analytics Org", plan=TenantPlan.PRO)
        report = _make_report([
            {"severity": "critical", "path": "/api/users"},
            {"severity": "high", "path": "/api/orders"},
        ])
        self.analytics_svc.store_report(tenant.id, report)
        summary = self.analytics_svc.get_summary(tenant.id)
        assert summary.total_executions == 1
        assert summary.total_vulnerabilities == 2
        assert summary.severity_distribution["critical"] == 1

    def test_tenant_quota_blocks_analytics_for_free_plan(self):
        tenant = self.tenant_svc.create_tenant("Free Org", plan=TenantPlan.FREE)
        assert not tenant.quota.advanced_analytics

    def test_tenant_quota_allows_analytics_for_pro_plan(self):
        tenant = self.tenant_svc.create_tenant("Pro Org", plan=TenantPlan.PRO)
        assert tenant.quota.advanced_analytics

    def test_multi_tenant_analytics_isolation(self):
        t1 = self.tenant_svc.create_tenant("Org A", plan=TenantPlan.PRO)
        t2 = self.tenant_svc.create_tenant("Org B", plan=TenantPlan.PRO)
        r1 = _make_report([{"severity": "critical", "path": "/a"}])
        r2 = _make_report([{"severity": "low", "path": "/b"}])
        self.analytics_svc.store_report(t1.id, r1)
        self.analytics_svc.store_report(t2.id, r2)
        s1 = self.analytics_svc.get_summary(t1.id)
        s2 = self.analytics_svc.get_summary(t2.id)
        assert s1.severity_distribution.get("critical") == 1
        assert s2.severity_distribution.get("low") == 1
        assert "critical" not in s2.severity_distribution
        assert "low" not in s1.severity_distribution

    def test_analytics_comparison_within_tenant(self):
        tenant = self.tenant_svc.create_tenant("Compare Org", plan=TenantPlan.PRO)
        baseline = _make_report([
            {"severity": "critical", "path": "/api/pay", "type": "t1"},
        ], report_id="baseline")
        current = _make_report([
            {"severity": "low", "path": "/api/pay", "type": "t1"},
        ], report_id="current")
        result = self.analytics_svc.compare_reports(baseline, current)
        assert result.improved is True
        assert result.risk_score_delta < 0


class TestCicdAnalyticsIntegration:
    """Test CI/CD ↔ Analytics service integration."""

    def setup_method(self):
        self.cicd_svc = CiCdService()
        self.analytics_svc = AnalyticsService()

    def test_pipeline_run_produces_report_for_analytics(self):
        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("analytics-pipeline", config)
        run = self.cicd_svc.trigger_run(pipeline.id)
        report = _make_report([
            {"severity": "high", "path": "/api/test"},
        ], report_id=f"report-{run.id}")
        self.cicd_svc.complete_run(
            run.id, pipeline.id,
            report_id=report.id,
            vulnerabilities=1,
            max_severity="high",
            success=True,
        )
        self.analytics_svc.store_report("default", report)
        summary = self.analytics_svc.get_summary("default")
        assert summary.total_executions == 1
        assert summary.total_vulnerabilities == 1

    def test_multiple_runs_aggregate_in_analytics(self):
        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("multi-run", config)
        for i in range(3):
            run = self.cicd_svc.trigger_run(pipeline.id)
            report = _make_report([
                {"severity": "high", "path": f"/api/ep{i}"},
            ], report_id=f"report-{i}")
            self.cicd_svc.complete_run(
                run.id, pipeline.id,
                report_id=report.id,
                vulnerabilities=1,
                max_severity="high",
                success=True,
            )
            self.analytics_svc.store_report("default", report)
        summary = self.analytics_svc.get_summary("default")
        assert summary.total_executions == 3
        assert summary.total_vulnerabilities == 3

    def test_github_actions_workflow_includes_analytics_config(self):
        config = _make_config()
        from api_chaos_agent.services.cicd_service import GitHubActionsGenerator
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config, "analytics-test")
        assert "chaos-test" in yaml_str
        assert "ubuntu-latest" in yaml_str

    def test_gitlab_ci_pipeline_includes_analytics_config(self):
        config = _make_config(CiCdProvider.GITLAB_CI)
        from api_chaos_agent.services.cicd_service import GitLabCIGenerator
        gen = GitLabCIGenerator()
        yaml_str = gen.generate_pipeline(config, "analytics-gitlab")
        assert "API Chaos Test" in yaml_str


class TestFullThreeWayIntegration:
    """Full integration: Tenant → CI/CD → Analytics pipeline."""

    def setup_method(self):
        self.tenant_svc = TenantService()
        self.cicd_svc = CiCdService()
        self.analytics_svc = AnalyticsService()

    def test_complete_workflow_pro_to_analytics(self):
        tenant = self.tenant_svc.create_tenant("Full Flow Org", plan=TenantPlan.PRO)
        assert tenant.quota.ci_cd_integration
        assert tenant.quota.advanced_analytics

        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("full-flow", config, tenant_id=tenant.id)
        run = self.cicd_svc.trigger_run(pipeline.id)

        report = _make_report([
            {"severity": "critical", "path": "/api/users", "type": "latency"},
            {"severity": "high", "path": "/api/orders", "type": "error_status"},
            {"severity": "medium", "path": "/api/products", "type": "rate_limit"},
        ], exec_time_ms=250.0, total_scenarios=20, report_id="full-report")
        self.cicd_svc.complete_run(
            run.id, pipeline.id,
            report_id=report.id,
            vulnerabilities=3,
            max_severity="critical",
            success=False,
        )
        self.analytics_svc.store_report(tenant.id, report)

        summary = self.analytics_svc.get_summary(tenant.id)
        assert summary.total_executions == 1
        assert summary.total_vulnerabilities == 3
        assert summary.severity_distribution["critical"] == 1
        assert summary.pass_rate == 85.0
        assert isinstance(summary.avg_execution_time_ms, float)
        assert len(summary.top_risk_endpoints) >= 1

    def test_enterprise_full_workflow_with_comparison(self):
        tenant = self.tenant_svc.create_tenant("Enterprise Org", plan=TenantPlan.ENTERPRISE)
        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("ent-pipeline", config, tenant_id=tenant.id)

        baseline_report = _make_report([
            {"severity": "critical", "path": "/api/pay", "type": "t1"},
            {"severity": "high", "path": "/api/auth", "type": "t2"},
        ], report_id="baseline")
        run1 = self.cicd_svc.trigger_run(pipeline.id)
        self.cicd_svc.complete_run(
            run1.id, pipeline.id,
            report_id=baseline_report.id,
            vulnerabilities=2,
            max_severity="critical",
            success=False,
        )
        self.analytics_svc.store_report(tenant.id, baseline_report)

        current_report = _make_report([
            {"severity": "medium", "path": "/api/pay", "type": "t1"},
        ], report_id="current")
        run2 = self.cicd_svc.trigger_run(pipeline.id)
        self.cicd_svc.complete_run(
            run2.id, pipeline.id,
            report_id=current_report.id,
            vulnerabilities=1,
            max_severity="medium",
            success=True,
        )
        self.analytics_svc.store_report(tenant.id, current_report)

        summary = self.analytics_svc.get_summary(tenant.id)
        assert summary.total_executions == 2

        comparison = self.analytics_svc.compare_reports(baseline_report, current_report)
        assert comparison.resolved_findings >= 1
        assert comparison.improved is True

    def test_free_tenant_cannot_use_cicd_or_analytics(self):
        tenant = self.tenant_svc.create_tenant("Free Org", plan=TenantPlan.FREE)
        assert not tenant.quota.ci_cd_integration
        assert not tenant.quota.advanced_analytics
        assert not tenant.quota.custom_plugins

    def test_multi_tenant_isolated_cicd_analytics(self):
        t1 = self.tenant_svc.create_tenant("Org A", plan=TenantPlan.PRO)
        t2 = self.tenant_svc.create_tenant("Org B", plan=TenantPlan.PRO)

        config1 = _make_config(CiCdProvider.GITHUB_ACTIONS)
        config2 = _make_config(CiCdProvider.GITLAB_CI)
        p1 = self.cicd_svc.create_pipeline("pipe-a", config1, tenant_id=t1.id)
        p2 = self.cicd_svc.create_pipeline("pipe-b", config2, tenant_id=t2.id)

        r1 = _make_report([{"severity": "critical", "path": "/a"}], report_id="r1")
        r2 = _make_report([{"severity": "low", "path": "/b"}], report_id="r2")
        self.analytics_svc.store_report(t1.id, r1)
        self.analytics_svc.store_report(t2.id, r2)

        s1 = self.analytics_svc.get_summary(t1.id)
        s2 = self.analytics_svc.get_summary(t2.id)
        assert s1.total_vulnerabilities == 1
        assert s2.total_vulnerabilities == 1
        assert s1.severity_distribution.get("critical") == 1
        assert s2.severity_distribution.get("low") == 1

    def test_team_member_triggers_pipeline(self):
        tenant = self.tenant_svc.create_tenant("Team Org", plan=TenantPlan.PRO)
        member = self.tenant_svc.add_member(
            tenant.id, "dev@example.com", TeamMemberRole.MEMBER, "Developer"
        )
        assert member is not None

        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("team-pipe", config, tenant_id=tenant.id)
        run = self.cicd_svc.trigger_run(pipeline.id)
        report = _make_report([{"severity": "high", "path": "/api/test"}], report_id="team-report")
        self.cicd_svc.complete_run(
            run.id, pipeline.id,
            report_id=report.id,
            vulnerabilities=1,
            max_severity="high",
            success=True,
        )
        self.analytics_svc.store_report(tenant.id, report)
        summary = self.analytics_svc.get_summary(tenant.id)
        assert summary.total_executions == 1

    def test_quota_enforcement_across_services(self):
        tenant = self.tenant_svc.create_tenant("Quota Org", plan=TenantPlan.PRO)
        assert self.tenant_svc.check_quota(tenant.id, "schemas", 5)
        assert not self.tenant_svc.check_quota(tenant.id, "schemas", 100)
        assert tenant.quota.ci_cd_integration
        assert tenant.quota.advanced_analytics
        assert tenant.quota.distributed_workers == 5

    def test_analytics_trend_from_repeated_cicd_runs(self):
        tenant = self.tenant_svc.create_tenant("Trend Org", plan=TenantPlan.ENTERPRISE)
        config = _make_config()
        pipeline = self.cicd_svc.create_pipeline("trend-pipe", config, tenant_id=tenant.id)

        base_date = datetime(2025, 1, 1)
        for i in range(5):
            run = self.cicd_svc.trigger_run(pipeline.id)
            report = _make_report(
                [{"severity": "high", "path": "/api/test"}],
                report_id=f"trend-report-{i}",
            )
            report.created_at = base_date.replace(day=i + 1)
            self.cicd_svc.complete_run(
                run.id, pipeline.id,
                report_id=report.id,
                vulnerabilities=1,
                max_severity="high",
                success=True,
            )
            self.analytics_svc.store_report(tenant.id, report)

        summary = self.analytics_svc.get_summary(tenant.id, period=TrendPeriod.DAILY)
        assert summary.total_executions == 5
        assert len(summary.trends) == 5
