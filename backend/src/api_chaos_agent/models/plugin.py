from __future__ import annotations

# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.


from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PluginStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class FaultPluginManifest(BaseModel):
    name: str = Field(description="Unique plugin identifier")
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    scenario_type: str = Field(description="Maps to ChaosScenarioType or custom")
    entry_point: str = Field(description="Python import path, e.g. my_plugin:MyFaultPlugin")
    config_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for plugin config")
    tags: list[str] = Field(default_factory=list)


class FaultPlugin(BaseModel):
    id: str = ""
    manifest: FaultPluginManifest
    status: PluginStatus = PluginStatus.ENABLED
    loaded_at: datetime = Field(default_factory=datetime.now)
    error_message: str | None = None
    execution_count: int = 0
    last_executed_at: datetime | None = None


class FaultPluginExecution(BaseModel):
    plugin_id: str
    scenario_id: str
    input_config: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None
    elapsed_ms: float = 0.0
