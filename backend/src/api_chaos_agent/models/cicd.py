"""CI/CD pipeline models.

Defines the data structures for CI/CD integration, including
pipeline configurations, runs, and provider types.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CiCdProvider(str, Enum):
    """Supported CI/CD providers."""

    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    JENKINS = "jenkins"
    CIRCLECI = "circleci"


class PipelineConfig(BaseModel):
    """Configuration for a CI/CD chaos testing pipeline."""

    provider: CiCdProvider = Field(description="CI/CD provider type")
    project_url: str = Field(default="", description="Project repository URL")
    branch: str = Field(default="main", description="Branch to monitor")
    api_spec_path: str = Field(default="openapi.yaml", description="Path to API spec in repo")
    scenario_types: list[str] = Field(default_factory=lambda: ["latency", "error_status"], description="Scenario types to run")
    fail_on_severity: str = Field(default="high", description="Fail pipeline if finding >= this severity")
    base_url: str = Field(default="", description="Target API base URL for testing")
    concurrency: int = Field(default=10, description="Concurrent scenario executions")
    timeout_seconds: float = Field(default=300.0, description="Overall pipeline timeout in seconds")
    headers: dict[str, str] = Field(default_factory=dict, description="Default HTTP headers")
    proxy: str | None = Field(default=None, description="HTTP proxy URL")
    schedule_cron: str | None = Field(default=None, description="Cron expression for scheduled runs")


class PipelineRun(BaseModel):
    """A single execution of a CI/CD pipeline."""

    id: str = Field(default="", description="Unique run identifier")
    pipeline_id: str = Field(description="Parent pipeline identifier")
    provider: CiCdProvider = Field(description="CI/CD provider")
    status: str = Field(default="pending", description="Run status: pending, running, completed, failed")
    triggered_at: datetime = Field(default_factory=datetime.now, description="Trigger timestamp")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp")
    commit_sha: str | None = Field(default=None, description="Git commit SHA that triggered the run")
    branch: str = Field(default="", description="Branch tested")
    report_id: str | None = Field(default=None, description="Associated report identifier")
    vulnerabilities_found: int = Field(default=0, description="Number of vulnerabilities found")
    max_severity: str | None = Field(default=None, description="Highest severity found")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional run metadata")


class Pipeline(BaseModel):
    """A CI/CD chaos testing pipeline configuration."""

    id: str = Field(default="", description="Unique pipeline identifier")
    tenant_id: str = Field(default="", description="Owning tenant identifier")
    name: str = Field(description="Pipeline display name")
    config: PipelineConfig = Field(description="Pipeline configuration")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    last_run_at: datetime | None = Field(default=None, description="Last run timestamp")
    last_run_status: str | None = Field(default=None, description="Last run status")
    enabled: bool = Field(default=True, description="Whether the pipeline is active")
