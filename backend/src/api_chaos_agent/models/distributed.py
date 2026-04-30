from __future__ import annotations

# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.


from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkerStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    OFFLINE = "offline"
    DRAINING = "draining"


class WorkerCapabilities(BaseModel):
    max_concurrency: int = 100
    supported_protocols: list[str] = Field(default_factory=lambda: ["rest"])
    region: str = "default"
    labels: dict[str, str] = Field(default_factory=dict)


class Worker(BaseModel):
    id: str = ""
    name: str = ""
    status: WorkerStatus = WorkerStatus.IDLE
    capabilities: WorkerCapabilities = Field(default_factory=WorkerCapabilities)
    registered_at: datetime = Field(default_factory=datetime.now)
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    current_task_id: str | None = None
    completed_tasks: int = 0
    failed_tasks: int = 0


class DistributedTask(BaseModel):
    id: str = ""
    execution_id: str
    worker_id: str | None = None
    scenario_ids: list[str] = Field(default_factory=list)
    status: str = "pending"
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_count: int = 0
    error_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DistributedExecutionPlan(BaseModel):
    execution_id: str
    total_scenarios: int = 0
    total_workers: int = 1
    tasks: list[DistributedTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    strategy: str = Field(default="round_robin", description="round_robin, least_loaded, region_aware")
