"""Unit tests for Phase 2: CI/CD Service."""

import pytest

from api_chaos_agent.models.cicd import CiCdProvider, PipelineConfig
from api_chaos_agent.services.cicd_service import CiCdService


class TestCiCdService:
    def setup_method(self):
        self.service = CiCdService()

    def test_create_pipeline(self):
        config = PipelineConfig(
            provider=CiCdProvider.GITHUB_ACTIONS,
            branch="main",
            api_spec_path="openapi.yaml",
            base_url="http://localhost:8080",
        )
        pipeline = self.service.create_pipeline("test-pipeline", config)
        assert pipeline.name == "test-pipeline"
        assert pipeline.config.provider == CiCdProvider.GITHUB_ACTIONS

    def test_list_pipelines(self):
        config = PipelineConfig(provider=CiCdProvider.GITLAB_CI)
        self.service.create_pipeline("p1", config)
        self.service.create_pipeline("p2", config)
        assert len(self.service.list_pipelines()) == 2

    def test_get_pipeline(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        pipeline = self.service.create_pipeline("test", config)
        found = self.service.get_pipeline(pipeline.id)
        assert found is not None
        assert found.name == "test"

    def test_delete_pipeline(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        pipeline = self.service.create_pipeline("to-delete", config)
        assert self.service.delete_pipeline(pipeline.id)
        assert self.service.get_pipeline(pipeline.id) is None

    def test_generate_github_actions_config(self):
        config = PipelineConfig(
            provider=CiCdProvider.GITHUB_ACTIONS,
            branch="main",
            api_spec_path="openapi.yaml",
            base_url="http://api.example.com",
            scenario_types=["latency", "error_status"],
        )
        pipeline = self.service.create_pipeline("gh-pipeline", config)
        yaml_config = self.service.generate_config(pipeline.id)
        assert yaml_config is not None
        assert "chaos-test" in yaml_config
        assert "actions/checkout" in yaml_config
        assert "openapi.yaml" in yaml_config

    def test_generate_gitlab_ci_config(self):
        config = PipelineConfig(
            provider=CiCdProvider.GITLAB_CI,
            branch="main",
            api_spec_path="openapi.yaml",
            base_url="http://api.example.com",
        )
        pipeline = self.service.create_pipeline("gl-pipeline", config)
        yaml_config = self.service.generate_config(pipeline.id)
        assert yaml_config is not None
        assert "chaos-test" in yaml_config
        assert "api-chaos-agent" in yaml_config

    def test_trigger_run(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        pipeline = self.service.create_pipeline("run-test", config)
        run = self.service.trigger_run(pipeline.id, commit_sha="abc123")
        assert run is not None
        assert run.status == "running"
        assert run.commit_sha == "abc123"

    def test_trigger_disabled_pipeline(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        pipeline = self.service.create_pipeline("disabled", config)
        pipeline.enabled = False
        run = self.service.trigger_run(pipeline.id)
        assert run is None

    def test_complete_run(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        pipeline = self.service.create_pipeline("comp-test", config)
        run = self.service.trigger_run(pipeline.id)
        completed = self.service.complete_run(
            run.id, pipeline.id, report_id="r1", vulnerabilities=3, max_severity="high"
        )
        assert completed is not None
        assert completed.status == "completed"
        assert completed.vulnerabilities_found == 3

    def test_get_runs(self):
        config = PipelineConfig(provider=CiCdProvider.GITHUB_ACTIONS)
        pipeline = self.service.create_pipeline("runs-test", config)
        self.service.trigger_run(pipeline.id)
        self.service.trigger_run(pipeline.id)
        runs = self.service.get_runs(pipeline.id)
        assert len(runs) == 2
