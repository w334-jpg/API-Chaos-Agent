from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_chaos_agent.models.schema import Endpoint


class ChaosScenarioType(str, Enum):
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
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class LatencyConfig(BaseModel):
    delay_ms: int = Field(ge=0, description="Delay in milliseconds")
    jitter_ms: int = Field(ge=0, default=0, description="Random jitter")


class ErrorStatusConfig(BaseModel):
    status_code: int = Field(ge=100, le=599)
    repeat_count: int = Field(ge=1, default=1)


class TamperingConfig(BaseModel):
    field_path: str
    tamper_type: str = Field(description="remove, replace, overflow, type_mismatch, inject")
    tamper_value: Any = None


class RateLimitConfig(BaseModel):
    requests_per_second: int = Field(ge=1)
    duration_seconds: int = Field(ge=1, default=10)


class ChaosScenario(BaseModel):
    id: str = Field(default_factory=lambda: "")
    name: str
    scenario_type: ChaosScenarioType
    endpoint: Endpoint
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    expected_behavior: str = ""
    severity: Severity = Severity.MEDIUM
