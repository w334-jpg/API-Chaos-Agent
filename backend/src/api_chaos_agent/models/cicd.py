from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CiCdProvider(str, Enum):
    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    JENKINS = "jenkins"
    CIRCLECI = "circleci"


class PipelineConfig(BaseModel):
    provider: CiCdProvider
    project_url: str = ""
    branch: str = "main"
    api_spec_path: str = Field(default="openapi.yaml", description="Path to API spec in repo")
    scenario_types: list[str] = Field(default_factory=lambda: ["latency", "error_status"])
    fail_on_severity: str = Field(default="high", description="Fail pipeline if finding >= this severity")
    base_url: str = ""
    concurrency: int = 10
    timeout_seconds: float = 300.0
    headers: dict[str, str] = Field(default_factory=dict)
    proxy: str | None = None
    schedule_cron: str | None = Field(None, description="Cron expression for scheduled runs")


class PipelineRun(BaseModel):
    id: str = ""
    pipeline_id: str
    provider: CiCdProvider
    status: str = "pending"
    triggered_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    commit_sha: str | None = None
    branch: str = ""
    report_id: str | None = None
    vulnerabilities_found: int = 0
    max_severity: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Pipeline(BaseModel):
    id: str = ""
    tenant_id: str = ""
    name: str
    config: PipelineConfig
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    enabled: bool = True
