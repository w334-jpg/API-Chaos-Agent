"""In-memory store for managing schemas, scenarios, executions, and reports.

Enhanced with:
- Thread-safe operations via asyncio.Lock
- Capacity limits per collection to prevent unbounded memory growth
- LRU-style eviction when capacity is exceeded
- Timestamp tracking for TTL-based expiry
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from typing import Any

from api_chaos_agent.core.config import settings
from api_chaos_agent.models.schema import APISpec
from api_chaos_agent.models.scenario import ChaosScenario
from api_chaos_agent.models.report import TestResult, Report


class _ExpiryOrderedDict(OrderedDict):
    """OrderedDict with timestamp tracking for TTL-based eviction."""

    def __init__(self, maxsize: int = 1000, ttl: float = 3600):
        super().__init__()
        self._maxsize = maxsize
        self._ttl = ttl
        self._timestamps: dict[str, float] = {}

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired_keys = [k for k, ts in self._timestamps.items() if now - ts > self._ttl]
        for k in expired_keys:
            self.pop(k, None)
            self._timestamps.pop(k, None)

    def _evict_oldest(self) -> None:
        while len(self) > self._maxsize:
            oldest_key, _ = self.popitem(last=False)
            self._timestamps.pop(oldest_key, None)

    def __setitem__(self, key: str, value: Any) -> None:
        self._evict_expired()
        super().__setitem__(key, value)
        self._timestamps[key] = time.monotonic()
        self._evict_oldest()

    def __getitem__(self, key: str) -> Any:
        self._evict_expired()
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        self._evict_expired()
        if key in self._timestamps:
            now = time.monotonic()
            if now - self._timestamps[key] > self._ttl:
                self.pop(key, None)
                self._timestamps.pop(key, None)
                return default
        return super().get(key, default)

    def clear(self) -> None:
        super().clear()
        self._timestamps.clear()


class InMemoryStore:
    """Thread-safe in-memory store for all application state.

    Features:
    - asyncio.Lock for safe concurrent access
    - Configurable capacity limits per collection
    - TTL-based automatic expiry
    - LRU eviction when capacity is exceeded
    """

    def __init__(
        self,
        max_schemas: int | None = None,
        max_scenarios: int | None = None,
        max_executions: int | None = None,
        max_reports: int | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        cfg = settings.store
        self._lock = asyncio.Lock()
        self._schemas = _ExpiryOrderedDict(
            maxsize=max_schemas or cfg.max_schemas,
            ttl=ttl_seconds or cfg.ttl_seconds,
        )
        self._scenarios = _ExpiryOrderedDict(
            maxsize=max_scenarios or cfg.max_scenarios,
            ttl=ttl_seconds or cfg.ttl_seconds,
        )
        self._executions = _ExpiryOrderedDict(
            maxsize=max_executions or cfg.max_executions,
            ttl=ttl_seconds or cfg.ttl_seconds,
        )
        self._reports = _ExpiryOrderedDict(
            maxsize=max_reports or cfg.max_reports,
            ttl=ttl_seconds or cfg.ttl_seconds,
        )

    async def save_schema(self, spec: APISpec) -> str:
        async with self._lock:
            if not spec.title and not spec.raw_spec:
                schema_id = str(uuid.uuid4())
            else:
                raw = f"{spec.title}::{spec.version}"
                schema_id = str(uuid.uuid5(uuid.NAMESPACE_URL, raw))
            self._schemas[schema_id] = spec
            return schema_id

    async def get_schema(self, schema_id: str) -> APISpec | None:
        return self._schemas.get(schema_id)

    async def list_schemas(self) -> dict[str, APISpec]:
        return dict(self._schemas)

    async def save_scenario(self, scenario: ChaosScenario) -> str:
        async with self._lock:
            if not scenario.id:
                scenario.id = str(uuid.uuid4())
            self._scenarios[scenario.id] = scenario
            return scenario.id

    async def get_scenario(self, scenario_id: str) -> ChaosScenario | None:
        return self._scenarios.get(scenario_id)

    async def list_scenarios(self) -> dict[str, ChaosScenario]:
        return dict(self._scenarios)

    async def save_execution(self, result: TestResult) -> str:
        async with self._lock:
            if not result.id:
                result.id = str(uuid.uuid4())
            self._executions[result.id] = result
            return result.id

    async def get_execution(self, execution_id: str) -> TestResult | None:
        return self._executions.get(execution_id)

    async def list_executions(self) -> dict[str, TestResult]:
        return dict(self._executions)

    async def save_report(self, report: Report) -> str:
        async with self._lock:
            if not report.id:
                report.id = str(uuid.uuid4())
            self._reports[report.id] = report
            return report.id

    async def get_report(self, report_id: str) -> Report | None:
        return self._reports.get(report_id)

    async def list_reports(self) -> dict[str, Report]:
        return dict(self._reports)

    async def clear(self) -> None:
        async with self._lock:
            self._schemas.clear()
            self._scenarios.clear()
            self._executions.clear()
            self._reports.clear()

    def clear_sync(self) -> None:
        self._schemas.clear()
        self._scenarios.clear()
        self._executions.clear()
        self._reports.clear()

    async def stats(self) -> dict[str, int]:
        return {
            "schemas": len(self._schemas),
            "scenarios": len(self._scenarios),
            "executions": len(self._executions),
            "reports": len(self._reports),
        }


def _create_store() -> InMemoryStore:
    return InMemoryStore()


def _create_persistent_store():
    from api_chaos_agent.services.sqlite_store import SQLiteStore
    return SQLiteStore()


def create_store():
    if settings.store.backend == "sqlite":
        return _create_persistent_store()
    return _create_store()


class _StoreProxy:
    """Lazy-loading store proxy that defers creation until first access.

    Respects ``settings.store.backend`` at runtime instead of import time,
    so the correct backend (memory / SQLite) is always selected.
    """

    def __init__(self) -> None:
        self._real: InMemoryStore | None = None

    def _ensure(self) -> InMemoryStore:
        if self._real is None:
            self._real = create_store()
        return self._real

    async def save_schema(self, spec: APISpec) -> str:
        return await self._ensure().save_schema(spec)

    async def get_schema(self, schema_id: str) -> APISpec | None:
        return await self._ensure().get_schema(schema_id)

    async def list_schemas(self) -> dict[str, APISpec]:
        return await self._ensure().list_schemas()

    async def save_scenario(self, scenario: ChaosScenario) -> str:
        return await self._ensure().save_scenario(scenario)

    async def get_scenario(self, scenario_id: str) -> ChaosScenario | None:
        return await self._ensure().get_scenario(scenario_id)

    async def list_scenarios(self) -> dict[str, ChaosScenario]:
        return await self._ensure().list_scenarios()

    async def save_execution(self, result: TestResult) -> str:
        return await self._ensure().save_execution(result)

    async def get_execution(self, execution_id: str) -> TestResult | None:
        return await self._ensure().get_execution(execution_id)

    async def list_executions(self) -> dict[str, TestResult]:
        return await self._ensure().list_executions()

    async def save_report(self, report: Report) -> str:
        return await self._ensure().save_report(report)

    async def get_report(self, report_id: str) -> Report | None:
        return await self._ensure().get_report(report_id)

    async def list_reports(self) -> dict[str, Report]:
        return await self._ensure().list_reports()

    async def clear(self) -> None:
        await self._ensure().clear()

    def clear_sync(self) -> None:
        if self._real is not None:
            self._real._schemas.clear()
            self._real._scenarios.clear()
            self._real._executions.clear()
            self._real._reports.clear()
        self._real = None

    async def stats(self) -> dict[str, int]:
        return await self._ensure().stats()


store = _StoreProxy()
