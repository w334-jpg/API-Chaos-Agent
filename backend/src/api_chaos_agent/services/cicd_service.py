# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""CI/CD Integration Service for API Chaos Agent.

Supports:
- GitHub Actions workflow generation and status tracking
- GitLab CI pipeline configuration generation
- Jenkins pipeline support
- Webhook-based pipeline triggering
- Scheduled execution via cron
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.cicd import (
    CiCdProvider,
    Pipeline,
    PipelineConfig,
    PipelineRun,
)

logger = get_logger(__name__)


class GitHubActionsGenerator:
    """Generate GitHub Actions workflow YAML for chaos testing."""

    def generate_workflow(self, config: PipelineConfig, pipeline_name: str = "chaos-test") -> str:
        "\n".join(f'          - "{t}"' for t in config.scenario_types)
        return f"""name: API Chaos Test - {pipeline_name}

on:
  push:
    branches: [ "{config.branch}" ]
  pull_request:
    branches: [ "{config.branch}" ]
  schedule:
    - cron: "{config.schedule_cron or "0 6 * * 1"}"
  workflow_dispatch:

jobs:
  chaos-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install API Chaos Agent
        run: pip install api-chaos-agent

      - name: Run Chaos Tests
        env:
          OPENAI_API_KEY: ${{{{ secrets.OPENAI_API_KEY }}}}
          ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
        run: |
          chaos-agent run \\
            --spec {config.api_spec_path} \\
            --base-url {config.base_url} \\
            --concurrency {config.concurrency} \\
            --timeout {config.timeout_seconds} \\
            --fail-on {config.fail_on_severity} \\
            --scenario-types {",".join(config.scenario_types)} \\
            --output-format json \\
            --output-path chaos-report.json

      - name: Upload Chaos Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: chaos-report
          path: chaos-report.json

      - name: Check Results
        run: |
          python -c "
          import json
          with open('chaos-report.json') as f:
              report = json.load(f)
          severity_order = ['info', 'low', 'medium', 'high', 'critical']
          fail_level = severity_order.index('{config.fail_on_severity}')
          for finding in report.get('findings', []):
              finding_level = severity_order.index(finding.get('severity', 'info'))
              if finding_level >= fail_level:
                  print(f'FAIL: {{finding[\"description\"]}}')
                  exit(1)
          print('All chaos tests passed!')
          "
"""


class GitLabCIGenerator:
    """Generate GitLab CI pipeline YAML for chaos testing."""

    def generate_pipeline(self, config: PipelineConfig, pipeline_name: str = "chaos-test") -> str:
        return f"""# API Chaos Test - {pipeline_name}
stages:
  - test

chaos-test:
  stage: test
  image: python:3.12-slim
  before_script:
    - pip install api-chaos-agent
  script:
    - |
      chaos-agent run \\
        --spec {config.api_spec_path} \\
        --base-url {config.base_url} \\
        --concurrency {config.concurrency} \\
        --timeout {config.timeout_seconds} \\
        --fail-on {config.fail_on_severity} \\
        --scenario-types {",".join(config.scenario_types)} \\
        --output-format json \\
        --output-path chaos-report.json
  artifacts:
    when: always
    paths:
      - chaos-report.json
    expire_in: 30 days
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
    - if: $CI_COMMIT_BRANCH == "{config.branch}"
  variables:
    OPENAI_API_KEY: $OPENAI_API_KEY
    ANTHROPIC_API_KEY: $ANTHROPIC_API_KEY
"""


class CiCdService:
    """Manage CI/CD pipeline integrations."""

    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}
        self._runs: dict[str, list[PipelineRun]] = {}
        self._generators: dict[CiCdProvider, Any] = {
            CiCdProvider.GITHUB_ACTIONS: GitHubActionsGenerator(),
            CiCdProvider.GITLAB_CI: GitLabCIGenerator(),
        }

    def create_pipeline(self, name: str, config: PipelineConfig, tenant_id: str = "") -> Pipeline:
        pipeline = Pipeline(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            config=config,
        )
        self._pipelines[pipeline.id] = pipeline
        self._runs[pipeline.id] = []
        logger.info(
            "pipeline_created", pipeline_id=pipeline.id, name=name, provider=config.provider.value
        )
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self, tenant_id: str = "") -> list[Pipeline]:
        pipelines = list(self._pipelines.values())
        if tenant_id:
            pipelines = [p for p in pipelines if p.tenant_id == tenant_id]
        return pipelines

    def delete_pipeline(self, pipeline_id: str) -> bool:
        if pipeline_id in self._pipelines:
            del self._pipelines[pipeline_id]
            self._runs.pop(pipeline_id, None)
            return True
        return False

    def generate_config(self, pipeline_id: str) -> str | None:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return None
        generator = self._generators.get(pipeline.config.provider)
        if not generator:
            return None
        if pipeline.config.provider == CiCdProvider.GITHUB_ACTIONS:
            return generator.generate_workflow(pipeline.config, pipeline.name)
        elif pipeline.config.provider == CiCdProvider.GITLAB_CI:
            return generator.generate_pipeline(pipeline.config, pipeline.name)
        return None

    def trigger_run(self, pipeline_id: str, commit_sha: str | None = None) -> PipelineRun | None:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline or not pipeline.enabled:
            return None
        run = PipelineRun(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            provider=pipeline.config.provider,
            status="running",
            commit_sha=commit_sha,
            branch=pipeline.config.branch,
        )
        self._runs.setdefault(pipeline_id, []).append(run)
        pipeline.last_run_at = time.monotonic()
        pipeline.last_run_status = "running"
        logger.info("pipeline_run_triggered", run_id=run.id, pipeline_id=pipeline_id)
        return run

    def complete_run(
        self,
        run_id: str,
        pipeline_id: str,
        report_id: str | None = None,
        vulnerabilities: int = 0,
        max_severity: str | None = None,
        success: bool = True,
    ) -> PipelineRun | None:
        runs = self._runs.get(pipeline_id, [])
        for run in runs:
            if run.id == run_id:
                run.status = "completed" if success else "failed"
                run.completed_at = time.monotonic()
                run.report_id = report_id
                run.vulnerabilities_found = vulnerabilities
                run.max_severity = max_severity
                pipeline = self._pipelines.get(pipeline_id)
                if pipeline:
                    pipeline.last_run_status = run.status
                return run
        return None

    def get_runs(self, pipeline_id: str) -> list[PipelineRun]:
        return self._runs.get(pipeline_id, [])
