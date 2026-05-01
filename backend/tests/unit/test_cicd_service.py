"""Enhanced TDD tests for Phase 2: CI/CD Service.

Covers: unit tests, functional tests, edge cases, stress tests.
"""

import time

import pytest

from api_chaos_agent.models.cicd import CiCdProvider, PipelineConfig, PipelineRun
from api_chaos_agent.services.cicd_service import CiCdService, GitHubActionsGenerator, GitLabCIGenerator


def _make_config(provider: CiCdProvider = CiCdProvider.GITHUB_ACTIONS, **kwargs) -> PipelineConfig:
    defaults = {
        "provider": provider,
        "project_url": "https://github.com/test/repo",
        "branch": "main",
        "api_spec_path": "openapi.yaml",
        "scenario_types": ["latency", "error_status"],
        "fail_on_severity": "high",
        "base_url": "https://api.test.com",
    }
    defaults.update(kwargs)
    return PipelineConfig(**defaults)


class TestCiCdServiceUnit:
    def setup_method(self):
        self.service = CiCdService()

    def test_create_pipeline(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("test-pipeline", config)
        assert pipeline.name == "test-pipeline"
        assert pipeline.config.provider == CiCdProvider.GITHUB_ACTIONS
        assert pipeline.enabled is True
        assert pipeline.id

    def test_get_pipeline(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("get-test", config)
        found = self.service.get_pipeline(pipeline.id)
        assert found is not None
        assert found.name == "get-test"

    def test_get_nonexistent_pipeline(self):
        assert self.service.get_pipeline("nonexistent") is None

    def test_list_pipelines(self):
        self.service.create_pipeline("p1", _make_config())
        self.service.create_pipeline("p2", _make_config(CiCdProvider.GITLAB_CI))
        assert len(self.service.list_pipelines()) == 2

    def test_list_pipelines_by_tenant(self):
        self.service.create_pipeline("p1", _make_config(), tenant_id="t1")
        self.service.create_pipeline("p2", _make_config(), tenant_id="t2")
        self.service.create_pipeline("p3", _make_config(), tenant_id="t1")
        assert len(self.service.list_pipelines(tenant_id="t1")) == 2
        assert len(self.service.list_pipelines(tenant_id="t2")) == 1

    def test_list_pipelines_empty_tenant(self):
        self.service.create_pipeline("p1", _make_config(), tenant_id="t1")
        assert len(self.service.list_pipelines(tenant_id="other")) == 0

    def test_delete_pipeline(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("del-test", config)
        assert self.service.delete_pipeline(pipeline.id)
        assert self.service.get_pipeline(pipeline.id) is None

    def test_delete_nonexistent_pipeline(self):
        assert not self.service.delete_pipeline("nonexistent")

    def test_delete_pipeline_clears_runs(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("del-runs", config)
        self.service.trigger_run(pipeline.id)
        self.service.delete_pipeline(pipeline.id)
        assert self.service.get_runs(pipeline.id) == []

    def test_trigger_run(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("trigger-test", config)
        run = self.service.trigger_run(pipeline.id)
        assert run is not None
        assert run.status == "running"
        assert run.pipeline_id == pipeline.id

    def test_trigger_run_with_commit(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("commit-test", config)
        run = self.service.trigger_run(pipeline.id, commit_sha="abc123")
        assert run.commit_sha == "abc123"

    def test_trigger_run_disabled_pipeline(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("disabled-test", config)
        pipeline.enabled = False
        run = self.service.trigger_run(pipeline.id)
        assert run is None

    def test_trigger_run_nonexistent_pipeline(self):
        run = self.service.trigger_run("nonexistent")
        assert run is None

    def test_complete_run_success(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("complete-test", config)
        run = self.service.trigger_run(pipeline.id)
        completed = self.service.complete_run(run.id, pipeline.id, report_id="r1", vulnerabilities=3, max_severity="high", success=True)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.report_id == "r1"
        assert completed.vulnerabilities_found == 3

    def test_complete_run_failure(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("fail-test", config)
        run = self.service.trigger_run(pipeline.id)
        completed = self.service.complete_run(run.id, pipeline.id, success=False)
        assert completed.status == "failed"

    def test_complete_run_nonexistent(self):
        result = self.service.complete_run("nonexistent", "nonexistent")
        assert result is None

    def test_get_runs(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("runs-test", config)
        self.service.trigger_run(pipeline.id)
        self.service.trigger_run(pipeline.id)
        runs = self.service.get_runs(pipeline.id)
        assert len(runs) == 2

    def test_get_runs_empty(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("no-runs", config)
        assert self.service.get_runs(pipeline.id) == []

    def test_pipeline_ids_are_unique(self):
        p1 = self.service.create_pipeline("p1", _make_config())
        p2 = self.service.create_pipeline("p2", _make_config())
        assert p1.id != p2.id

    def test_run_ids_are_unique(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("unique-runs", config)
        r1 = self.service.trigger_run(pipeline.id)
        r2 = self.service.trigger_run(pipeline.id)
        assert r1.id != r2.id


class TestGitHubActionsGenerator:
    def test_generate_workflow(self):
        config = _make_config()
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config, "test-workflow")
        assert "name: API Chaos Test - test-workflow" in yaml_str
        assert "chaos-test" in yaml_str
        assert "ubuntu-latest" in yaml_str
        assert "api-chaos-agent" in yaml_str

    def test_generate_workflow_contains_scenario_types(self):
        config = _make_config(scenario_types=["latency", "error_status", "network_partition"])
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config)
        assert "latency" in yaml_str
        assert "error_status" in yaml_str
        assert "network_partition" in yaml_str

    def test_generate_workflow_contains_schedule(self):
        config = _make_config(schedule_cron="0 6 * * 1")
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config)
        assert "0 6 * * 1" in yaml_str

    def test_generate_workflow_default_schedule(self):
        config = _make_config()
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config)
        assert "0 6 * * 1" in yaml_str

    def test_generate_workflow_custom_branch(self):
        config = _make_config(branch="develop")
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config)
        assert "develop" in yaml_str

    def test_generate_workflow_custom_concurrency(self):
        config = _make_config(concurrency=50)
        gen = GitHubActionsGenerator()
        yaml_str = gen.generate_workflow(config)
        assert "50" in yaml_str


class TestGitLabCIGenerator:
    def test_generate_pipeline(self):
        config = _make_config(CiCdProvider.GITLAB_CI)
        gen = GitLabCIGenerator()
        yaml_str = gen.generate_pipeline(config, "gitlab-test")
        assert "API Chaos Test - gitlab-test" in yaml_str
        assert "python:3.12-slim" in yaml_str
        assert "api-chaos-agent" in yaml_str

    def test_generate_pipeline_contains_scenario_types(self):
        config = _make_config(CiCdProvider.GITLAB_CI, scenario_types=["latency", "error_status"])
        gen = GitLabCIGenerator()
        yaml_str = gen.generate_pipeline(config)
        assert "latency" in yaml_str

    def test_generate_pipeline_custom_branch(self):
        config = _make_config(CiCdProvider.GITLAB_CI, branch="staging")
        gen = GitLabCIGenerator()
        yaml_str = gen.generate_pipeline(config)
        assert "staging" in yaml_str


class TestCiCdServiceGenerateConfig:
    def test_generate_github_actions_config(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("gh-config", config)
        yaml_str = self.service.generate_config(pipeline.id)
        assert yaml_str is not None
        assert "chaos-test" in yaml_str

    def test_generate_gitlab_ci_config(self):
        config = _make_config(CiCdProvider.GITLAB_CI)
        pipeline = self.service.create_pipeline("gl-config", config)
        yaml_str = self.service.generate_config(pipeline.id)
        assert yaml_str is not None
        assert "chaos-test" in yaml_str

    def test_generate_nonexistent_pipeline(self):
        assert self.service.generate_config("nonexistent") is None

    def setup_method(self):
        self.service = CiCdService()


class TestCiCdServiceEdgeCases:
    def setup_method(self):
        self.service = CiCdService()

    def test_multiple_runs_same_pipeline(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("multi-run", config)
        runs = [self.service.trigger_run(pipeline.id) for _ in range(5)]
        assert len(self.service.get_runs(pipeline.id)) == 5
        for run in runs:
            self.service.complete_run(run.id, pipeline.id, success=True)
        all_runs = self.service.get_runs(pipeline.id)
        assert all(r.status == "completed" for r in all_runs)

    def test_pipeline_last_run_status_updated(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("status-update", config)
        run = self.service.trigger_run(pipeline.id)
        assert pipeline.last_run_status == "running"
        self.service.complete_run(run.id, pipeline.id, success=True)
        assert pipeline.last_run_status == "completed"

    def test_pipeline_serialization(self):
        config = _make_config()
        pipeline = self.service.create_pipeline("serial-test", config)
        data = pipeline.model_dump()
        assert data["name"] == "serial-test"
        assert data["config"]["provider"] == "github_actions"

    def test_pipeline_config_defaults(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        assert config.branch == "main"
        assert config.api_spec_path == "openapi.yaml"
        assert config.concurrency == 10
        assert config.timeout_seconds == 300.0
        assert config.fail_on_severity == "high"

    def test_pipeline_run_defaults(self):
        run = PipelineRun(pipeline_id="p1", provider=CiCdProvider.GITHUB_ACTIONS)
        assert run.status == "pending"
        assert run.vulnerabilities_found == 0


class TestCiCdServiceStress:
    def test_create_many_pipelines(self):
        service = CiCdService()
        for i in range(100):
            service.create_pipeline(f"pipeline-{i}", _make_config())
        assert len(service.list_pipelines()) == 100

    def test_many_runs_per_pipeline(self):
        service = CiCdService()
        config = _make_config()
        pipeline = service.create_pipeline("stress-runs", config)
        for _ in range(100):
            service.trigger_run(pipeline.id)
        assert len(service.get_runs(pipeline.id)) == 100

    def test_create_pipeline_performance(self):
        service = CiCdService()
        start = time.monotonic()
        for i in range(200):
            service.create_pipeline(f"perf-{i}", _make_config())
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Creating 200 pipelines took {elapsed:.3f}s"

    def test_generate_config_performance(self):
        service = CiCdService()
        config = _make_config()
        pipeline = service.create_pipeline("gen-perf", config)
        start = time.monotonic()
        for _ in range(100):
            service.generate_config(pipeline.id)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Generating 100 configs took {elapsed:.3f}s"
