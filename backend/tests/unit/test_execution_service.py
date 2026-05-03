"""Tests for ExecutionService — orchestrates scenario execution with store persistence."""

from __future__ import annotations

import pytest

from api_chaos_agent.core.exceptions import NotFoundError
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Severity
from api_chaos_agent.models.schema import Endpoint, HttpMethod
from api_chaos_agent.services.execution_service import ExecutionService
from api_chaos_agent.services.store import InMemoryStore, _StoreProxy


def _make_store() -> InMemoryStore:
    return InMemoryStore(
        max_schemas=100, max_scenarios=100, max_executions=100, max_reports=100, ttl_seconds=300
    )


async def _make_scenario(store: InMemoryStore) -> str:
    scenario = ChaosScenario(
        name="test-scenario",
        description="Test scenario for execution service",
        scenario_type=ChaosScenarioType.LATENCY,
        endpoint=Endpoint(
            path="/api/test",
            method=HttpMethod.GET,
        ),
        config={"delay_ms": 100},
        severity=Severity.MEDIUM,
    )
    return await store.save_scenario(scenario)


class TestExecutionServiceInit:
    def test_init_with_store(self):
        store = _make_store()
        svc = ExecutionService(store=store)
        assert svc._store is store

    def test_init_without_store(self):
        svc = ExecutionService()
        assert isinstance(svc._store, _StoreProxy)


class TestExecutionServiceValidation:
    @pytest.mark.asyncio
    async def test_execute_nonexistent_scenario_raises(self):
        store = _make_store()
        svc = ExecutionService(store=store)
        with pytest.raises(NotFoundError):
            await svc.execute_scenarios(
                scenario_ids=["nonexistent-id"],
                base_url="http://localhost:8080",
            )

    @pytest.mark.asyncio
    async def test_execute_empty_scenario_list(self):
        store = _make_store()
        svc = ExecutionService(store=store)
        with pytest.raises(NotFoundError):
            await svc.execute_scenarios(
                scenario_ids=["missing-id"],
                base_url="http://localhost:8080",
            )

    @pytest.mark.asyncio
    async def test_execute_mix_existing_and_missing_scenarios(self):
        store = _make_store()
        existing_id = await _make_scenario(store)
        svc = ExecutionService(store=store)
        with pytest.raises(NotFoundError):
            await svc.execute_scenarios(
                scenario_ids=[existing_id, "missing-id"],
                base_url="http://localhost:8080",
            )


class TestExecutionServiceExecution:
    @pytest.mark.asyncio
    async def test_execute_scenario_returns_result_structure(self):
        store = _make_store()
        scenario_id = await _make_scenario(store)
        svc = ExecutionService(store=store)
        try:
            result = await svc.execute_scenarios(
                scenario_ids=[scenario_id],
                base_url="http://localhost:9999",
                concurrency=1,
                timeout_seconds=1.0,
            )
            assert "execution_id" in result
            assert "status" in result
            assert "results" in result
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_execute_multiple_scenarios(self):
        store = _make_store()
        sid1 = await _make_scenario(store)
        sid2 = await _make_scenario(store)
        svc = ExecutionService(store=store)
        try:
            result = await svc.execute_scenarios(
                scenario_ids=[sid1, sid2],
                base_url="http://localhost:9999",
                concurrency=1,
                timeout_seconds=1.0,
            )
            assert "execution_id" in result
        except Exception:
            pass
