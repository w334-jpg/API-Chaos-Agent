"""Fault plugin models.

Defines the data structures for the plugin framework, including
plugin manifests, status, and execution results.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PluginStatus(str, Enum):
    """Lifecycle status of a fault plugin."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class FaultPluginManifest(BaseModel):
    """Metadata describing a fault plugin's capabilities and configuration."""

    name: str = Field(description="Unique plugin identifier")
    version: str = Field(default="1.0.0", description="Plugin version (semver)")
    description: str = Field(default="", description="Human-readable plugin description")
    author: str = Field(default="", description="Plugin author")
    scenario_type: str = Field(description="Maps to ChaosScenarioType or custom type identifier")
    entry_point: str = Field(description="Python import path, e.g. my_plugin:MyFaultPlugin")
    config_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for plugin config validation")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")


class FaultPlugin(BaseModel):
    """Runtime state of a loaded fault plugin."""

    id: str = Field(default="", description="Unique runtime instance identifier")
    manifest: FaultPluginManifest = Field(description="Plugin manifest metadata")
    status: PluginStatus = Field(default=PluginStatus.ENABLED, description="Current plugin status")
    loaded_at: datetime = Field(default_factory=datetime.now, description="Timestamp when plugin was loaded")
    error_message: str | None = Field(default=None, description="Error message if status is ERROR")
    execution_count: int = Field(default=0, description="Number of times the plugin has been executed")
    last_executed_at: datetime | None = Field(default=None, description="Timestamp of last execution")


class FaultPluginExecution(BaseModel):
    """Result of a single fault plugin execution."""

    plugin_id: str = Field(description="Identifier of the executed plugin")
    scenario_id: str = Field(description="Identifier of the associated scenario")
    input_config: dict[str, Any] = Field(default_factory=dict, description="Configuration passed to the plugin")
    output: dict[str, Any] = Field(default_factory=dict, description="Plugin execution output")
    success: bool = Field(default=True, description="Whether the execution succeeded")
    error: str | None = Field(default=None, description="Error message if execution failed")
    elapsed_ms: float = Field(default=0.0, description="Execution duration in milliseconds")
