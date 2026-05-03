"""Tests for StoreProtocol — verifies the Protocol contract and runtime_checkable behavior."""

from __future__ import annotations

import pytest

from api_chaos_agent.core.store_protocol import StoreProtocol
from api_chaos_agent.services.store import InMemoryStore


class TestStoreProtocolContract:
    def test_in_memory_store_satisfies_protocol(self):
        store = InMemoryStore(
            max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
        )
        assert isinstance(store, StoreProtocol)

    def test_protocol_is_runtime_checkable(self):
        assert issubclass(InMemoryStore, StoreProtocol)

    def test_missing_method_fails_protocol_check(self):
        class IncompleteStore:
            pass

        assert not isinstance(IncompleteStore(), StoreProtocol)

    def test_partial_implementation_fails_protocol_check(self):
        class PartialStore:
            async def save_schema(self, spec): ...

        assert not isinstance(PartialStore(), StoreProtocol)

    @pytest.mark.asyncio
    async def test_protocol_methods_are_callable(self):
        store = InMemoryStore(
            max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
        )
        from api_chaos_agent.models.schema import APISpec, Endpoint, HttpMethod

        spec = APISpec(
            title="test-api",
            version="1.0.0",
            endpoints=[
                Endpoint(
                    path="/test",
                    method=HttpMethod.GET,
                )
            ],
        )
        schema_id = await store.save_schema(spec)
        assert schema_id is not None
        retrieved = await store.get_schema(schema_id)
        assert retrieved is not None
        assert retrieved.title == "test-api"

    @pytest.mark.asyncio
    async def test_protocol_stats_method(self):
        store = InMemoryStore(
            max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
        )
        stats = await store.stats()
        assert isinstance(stats, dict)
        assert "schemas" in stats

    @pytest.mark.asyncio
    async def test_protocol_clear_method(self):
        store = InMemoryStore(
            max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
        )
        await store.clear()
        stats = await store.stats()
        assert all(v == 0 for v in stats.values())

    @pytest.mark.asyncio
    async def test_protocol_list_methods_return_dict(self):
        store = InMemoryStore(
            max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
        )
        schemas = await store.list_schemas()
        assert isinstance(schemas, dict)
        scenarios = await store.list_scenarios()
        assert isinstance(scenarios, dict)
        executions = await store.list_executions()
        assert isinstance(executions, dict)
        reports = await store.list_reports()
        assert isinstance(reports, dict)

    @pytest.mark.asyncio
    async def test_protocol_get_nonexistent_returns_none(self):
        store = InMemoryStore(
            max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
        )
        assert await store.get_schema("nonexistent") is None
        assert await store.get_scenario("nonexistent") is None
        assert await store.get_execution("nonexistent") is None
        assert await store.get_report("nonexistent") is None
