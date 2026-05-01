"""Chaos scenario models.

Defines the data structures for chaos engineering scenarios, including
scenario types, severity levels, and type-specific configuration models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_chaos_agent.models.schema import Endpoint


class ChaosScenarioType(str, Enum):
    """Types of chaos scenarios that can be injected."""

    LATENCY = "latency"
    ERROR_STATUS = "error_status"
    REQUEST_TAMPERING = "request_tampering"
    RATE_LIMIT = "rate_limit"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DATA_CORRUPTION = "data_corruption"
    DEPENDENCY_FAILURE = "dependency_failure"
    NETWORK_PARTITION = "network_partition"
    CUSTOM_PLUGIN = "custom_plugin"


class Severity(str, Enum):
    """Severity levels for chaos test findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class LatencyConfig(BaseModel):
    """Configuration for latency injection scenarios."""

    delay_ms: int = Field(ge=0, description="Delay in milliseconds")
    jitter_ms: int = Field(ge=0, default=0, description="Random jitter in milliseconds")


class ErrorStatusConfig(BaseModel):
    """Configuration for error status injection scenarios."""

    status_code: int = Field(ge=100, le=599, description="HTTP status code to inject")
    repeat_count: int = Field(ge=1, default=1, description="Number of times to repeat the error")


class TamperingConfig(BaseModel):
    """Configuration for request tampering scenarios."""

    field_path: str = Field(description="JSON path of the field to tamper")
    tamper_type: str = Field(description="Tampering method: remove, replace, overflow, type_mismatch, inject")
    tamper_value: Any = Field(default=None, description="Value to use for replacement tampering")


class RateLimitConfig(BaseModel):
    """Configuration for rate limit testing scenarios."""

    requests_per_second: int = Field(ge=1, description="Number of requests per second to send")
    duration_seconds: int = Field(ge=1, default=10, description="Duration of the rate limit test")


class ChaosScenario(BaseModel):
    """A chaos engineering scenario to be executed against an API endpoint."""

    id: str = Field(default_factory=lambda: "", description="Unique scenario identifier")
    name: str = Field(description="Human-readable scenario name")
    scenario_type: ChaosScenarioType = Field(description="Type of chaos scenario")
    endpoint: Endpoint = Field(description="Target API endpoint")
    description: str = Field(default="", description="Detailed scenario description")
    config: dict[str, Any] = Field(default_factory=dict, description="Type-specific scenario configuration")
    expected_behavior: str = Field(default="", description="Expected API behavior under chaos")
    severity: Severity = Field(default=Severity.MEDIUM, description="Severity level of the scenario")
