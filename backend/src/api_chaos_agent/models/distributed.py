"""Distributed execution models.

Defines the data structures for distributed chaos test execution,
including workers, tasks, and execution plans.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkerStatus(str, Enum):
    """Status of a distributed execution worker."""

    IDLE = "idle"
    RUNNING = "running"
    OFFLINE = "offline"
    DRAINING = "draining"


class WorkerCapabilities(BaseModel):
    """Capabilities and constraints of a distributed worker."""

    max_concurrency: int = Field(default=100, description="Maximum concurrent scenario executions")
    supported_protocols: list[str] = Field(default_factory=lambda: ["rest"], description="Supported API protocols")
    region: str = Field(default="default", description="Geographic region for region-aware scheduling")
    labels: dict[str, str] = Field(default_factory=dict, description="Custom labels for filtering and routing")


class Worker(BaseModel):
    """A registered distributed execution worker."""

    id: str = Field(default="", description="Unique worker identifier")
    name: str = Field(default="", description="Human-readable worker name")
    status: WorkerStatus = Field(default=WorkerStatus.IDLE, description="Current worker status")
    capabilities: WorkerCapabilities = Field(default_factory=WorkerCapabilities, description="Worker capabilities")
    registered_at: datetime = Field(default_factory=datetime.now, description="Registration timestamp")
    last_heartbeat: datetime = Field(default_factory=datetime.now, description="Last heartbeat timestamp")
    current_task_id: str | None = Field(default=None, description="ID of currently assigned task")
    completed_tasks: int = Field(default=0, description="Total completed tasks")
    failed_tasks: int = Field(default=0, description="Total failed tasks")


class DistributedTask(BaseModel):
    """A task assigned to a distributed worker."""

    id: str = Field(default="", description="Unique task identifier")
    execution_id: str = Field(description="Parent execution plan identifier")
    worker_id: str | None = Field(default=None, description="Assigned worker identifier")
    scenario_ids: list[str] = Field(default_factory=list, description="Scenario identifiers in this task")
    status: str = Field(default="pending", description="Task status: pending, running, completed, failed")
    assigned_at: datetime | None = Field(default=None, description="Task assignment timestamp")
    started_at: datetime | None = Field(default=None, description="Task start timestamp")
    completed_at: datetime | None = Field(default=None, description="Task completion timestamp")
    result_count: int = Field(default=0, description="Number of successful results")
    error_count: int = Field(default=0, description="Number of errors")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional task metadata")


class DistributedExecutionPlan(BaseModel):
    """Execution plan for distributing scenarios across workers."""

    execution_id: str = Field(description="Unique execution identifier")
    total_scenarios: int = Field(default=0, description="Total number of scenarios to execute")
    total_workers: int = Field(default=1, description="Number of workers in the plan")
    tasks: list[DistributedTask] = Field(default_factory=list, description="Task assignments")
    created_at: datetime = Field(default_factory=datetime.now, description="Plan creation timestamp")
    strategy: str = Field(default="round_robin", description="Distribution strategy: round_robin, least_loaded, region_aware")
