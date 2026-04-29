"""Unit tests for InMemoryStore."""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio

from api_chaos_agent.models.schema import APISpec, Endpoint, HttpMethod
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Severity
from api_chaos_agent.models.report import TestResult, Report
from api_chaos_agent.services.store import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore(max_schemas=5, max_scenarios=5, max_executions=5, max_reports=5, ttl_seconds=60)


@pytest.mark.asyncio
async def test_save_and_get_schema(store: InMemoryStore) -> None:
    spec = APISpec(title="Test API", version="1.0.0")
    schema_id = await store.save_schema(spec)
    assert schema_id is not None

    retrieved = await store.get_schema(schema_id)
    assert retrieved is not None
    assert retrieved.title == "Test API"
    assert retrieved.version == "1.0.0"


@pytest.mark.asyncio
async def test_get_nonexistent_schema(store: InMemoryStore) -> None:
    result = await store.get_schema("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_schemas(store: InMemoryStore) -> None:
    spec1 = APISpec(title="API 1", version="1.0")
    spec2 = APISpec(title="API 2", version="2.0")
    await store.save_schema(spec1)
    await store.save_schema(spec2)

    schemas = await store.list_schemas()
    assert len(schemas) == 2


@pytest.mark.asyncio
async def test_capacity_eviction() -> None:
    s = InMemoryStore(max_schemas=3, ttl_seconds=600)
    for i in range(5):
        await s.save_schema(APISpec(title=f"API {i}", version="1.0"))

    schemas = await s.list_schemas()
    assert len(schemas) <= 3


@pytest.mark.asyncio
async def test_ttl_expiry() -> None:
    s = InMemoryStore(max_schemas=10, ttl_seconds=0.05)
    spec = APISpec(title="Expiring", version="1.0")
    schema_id = await s.save_schema(spec)

    await asyncio.sleep(0.1)
    result = await s.get_schema(schema_id)
    assert result is None


@pytest.mark.asyncio
async def test_save_and_get_scenario(store: InMemoryStore) -> None:
    endpoint = Endpoint(path="/test", method=HttpMethod.GET)
    scenario = ChaosScenario(
        name="Test Scenario",
        scenario_type=ChaosScenarioType.LATENCY,
        endpoint=endpoint,
        config={"delay_ms": 100},
        severity=Severity.LOW,
    )
    scenario_id = await store.save_scenario(scenario)
    assert scenario_id is not None

    retrieved = await store.get_scenario(scenario_id)
    assert retrieved is not None
    assert retrieved.name == "Test Scenario"


@pytest.mark.asyncio
async def test_save_and_get_execution(store: InMemoryStore) -> None:
    result = TestResult(total_scenarios=5)
    execution_id = await store.save_execution(result)
    assert execution_id is not None

    retrieved = await store.get_execution(execution_id)
    assert retrieved is not None
    assert retrieved.total_scenarios == 5


@pytest.mark.asyncio
async def test_save_and_get_report(store: InMemoryStore) -> None:
    report = Report(title="Test Report", total_scenarios=3)
    report_id = await store.save_report(report)
    assert report_id is not None

    retrieved = await store.get_report(report_id)
    assert retrieved is not None
    assert retrieved.title == "Test Report"


@pytest.mark.asyncio
async def test_stats(store: InMemoryStore) -> None:
    await store.save_schema(APISpec(title="S1", version="1.0"))
    await store.save_schema(APISpec(title="S2", version="1.0"))

    stats = await store.stats()
    assert stats["schemas"] == 2
    assert stats["scenarios"] == 0


@pytest.mark.asyncio
async def test_clear(store: InMemoryStore) -> None:
    await store.save_schema(APISpec(title="S1", version="1.0"))
    await store.clear()
    stats = await store.stats()
    assert stats["schemas"] == 0


@pytest.mark.asyncio
async def test_concurrent_writes() -> None:
    s = InMemoryStore(max_schemas=100, ttl_seconds=600)

    async def write_schema(idx: int) -> str:
        return await s.save_schema(APISpec(title=f"Concurrent {idx}", version="1.0"))

    results = await asyncio.gather(*[write_schema(i) for i in range(20)])
    assert len(results) == 20
    assert len(set(results)) == 20

    schemas = await s.list_schemas()
    assert len(schemas) == 20


@pytest.mark.asyncio
async def test_deterministic_id() -> None:
    s = InMemoryStore(max_schemas=100, ttl_seconds=600)
    spec = APISpec(title="Deterministic", version="1.0")
    id1 = await s.save_schema(spec)
    id2 = await s.save_schema(spec)
    assert id1 == id2
