"""Tests for SQLiteStore — persistent SQLite-backed store."""

from __future__ import annotations

import os
import tempfile

import pytest

from api_chaos_agent.models.report import (
    ExecutionStatus,
    Report,
    ReportSummary,
    ScenarioResult,
    TestResult,
)
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Severity
from api_chaos_agent.models.schema import APISpec, Endpoint, HttpMethod
from api_chaos_agent.services.sqlite_store import SQLiteStore


def _make_store() -> SQLiteStore:
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    return SQLiteStore(db_path=db_path)


def _make_spec() -> APISpec:
    return APISpec(
        title="Test API",
        version="1.0.0",
        endpoints=[Endpoint(path="/test", method=HttpMethod.GET)],
    )


def _make_scenario() -> ChaosScenario:
    return ChaosScenario(
        name="test-scenario",
        description="Test",
        scenario_type=ChaosScenarioType.LATENCY,
        endpoint=Endpoint(path="/api/test", method=HttpMethod.GET),
        config={"delay_ms": 100},
        severity=Severity.MEDIUM,
    )


def _make_scenario_result() -> ScenarioResult:
    return ScenarioResult(
        scenario_id="test-scenario",
        scenario_name="Test Scenario",
        scenario_type="latency",
        status=ExecutionStatus.COMPLETED,
    )


def _make_report() -> Report:
    return Report(
        id="test-report",
        schema_id="test-schema",
        summary=ReportSummary(
            total_scenarios=1,
            passed=1,
            failed=0,
        ),
    )


def _make_test_result() -> TestResult:
    return TestResult(
        id="",
        total_scenarios=1,
        completed_scenarios=1,
        results=[_make_scenario_result()],
    )


class TestSQLiteStoreInit:
    def test_init_creates_db(self):
        store = _make_store()
        assert store._conn is not None
        store.close()

    def test_init_creates_parent_dir(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "subdir", "test.db")
        store = SQLiteStore(db_path=db_path)
        assert store._conn is not None
        store.close()


class TestSQLiteStoreSchema:
    @pytest.mark.asyncio
    async def test_save_and_get_schema(self):
        store = _make_store()
        spec = _make_spec()
        sid = await store.save_schema(spec)
        retrieved = await store.get_schema(sid)
        assert retrieved is not None
        assert retrieved.title == "Test API"
        store.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_schema(self):
        store = _make_store()
        assert await store.get_schema("nonexistent") is None
        store.close()

    @pytest.mark.asyncio
    async def test_list_schemas(self):
        store = _make_store()
        await store.save_schema(_make_spec())
        await store.save_schema(_make_spec())
        schemas = await store.list_schemas()
        assert len(schemas) == 2
        store.close()


class TestSQLiteStoreScenario:
    @pytest.mark.asyncio
    async def test_save_and_get_scenario(self):
        store = _make_store()
        scenario = _make_scenario()
        sid = await store.save_scenario(scenario)
        retrieved = await store.get_scenario(sid)
        assert retrieved is not None
        assert retrieved.name == "test-scenario"
        store.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_scenario(self):
        store = _make_store()
        assert await store.get_scenario("nonexistent") is None
        store.close()

    @pytest.mark.asyncio
    async def test_list_scenarios(self):
        store = _make_store()
        await store.save_scenario(_make_scenario())
        scenarios = await store.list_scenarios()
        assert len(scenarios) == 1
        store.close()


class TestSQLiteStoreExecution:
    @pytest.mark.asyncio
    async def test_save_and_get_execution(self):
        store = _make_store()
        result = _make_test_result()
        eid = await store.save_execution(result)
        retrieved = await store.get_execution(eid)
        assert retrieved is not None
        assert retrieved.total_scenarios == 1
        store.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_execution(self):
        store = _make_store()
        assert await store.get_execution("nonexistent") is None
        store.close()

    @pytest.mark.asyncio
    async def test_list_executions(self):
        store = _make_store()
        await store.save_execution(_make_test_result())
        executions = await store.list_executions()
        assert len(executions) == 1
        store.close()


class TestSQLiteStoreReport:
    @pytest.mark.asyncio
    async def test_save_and_get_report(self):
        store = _make_store()
        report = _make_report()
        rid = await store.save_report(report)
        retrieved = await store.get_report(rid)
        assert retrieved is not None
        assert retrieved.id == "test-report"
        store.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_report(self):
        store = _make_store()
        assert await store.get_report("nonexistent") is None
        store.close()

    @pytest.mark.asyncio
    async def test_list_reports(self):
        store = _make_store()
        await store.save_report(_make_report())
        reports = await store.list_reports()
        assert len(reports) == 1
        store.close()


class TestSQLiteStoreClearAndStats:
    @pytest.mark.asyncio
    async def test_clear(self):
        store = _make_store()
        await store.save_schema(_make_spec())
        await store.save_scenario(_make_scenario())
        await store.clear()
        stats = await store.stats()
        assert all(v == 0 for v in stats.values())
        store.close()

    @pytest.mark.asyncio
    async def test_stats(self):
        store = _make_store()
        await store.save_schema(_make_spec())
        stats = await store.stats()
        assert stats["schemas"] == 1
        assert stats["scenarios"] == 0
        store.close()


class TestSQLiteStoreIterators:
    @pytest.mark.asyncio
    async def test_iter_schemas(self):
        store = _make_store()
        await store.save_schema(_make_spec())
        items = []
        async for item in store.iter_schemas():
            items.append(item)
        assert len(items) == 1
        store.close()

    @pytest.mark.asyncio
    async def test_iter_scenarios(self):
        store = _make_store()
        await store.save_scenario(_make_scenario())
        items = []
        async for item in store.iter_scenarios():
            items.append(item)
        assert len(items) == 1
        store.close()

    @pytest.mark.asyncio
    async def test_iter_executions(self):
        store = _make_store()
        await store.save_execution(_make_test_result())
        items = []
        async for item in store.iter_executions():
            items.append(item)
        assert len(items) == 1
        store.close()

    @pytest.mark.asyncio
    async def test_iter_reports(self):
        store = _make_store()
        await store.save_report(_make_report())
        items = []
        async for item in store.iter_reports():
            items.append(item)
        assert len(items) == 1
        store.close()


class TestSQLiteStoreClose:
    def test_close(self):
        store = _make_store()
        store.close()
        assert store._conn is None

    def test_close_idempotent(self):
        store = _make_store()
        store.close()
        store.close()
        assert store._conn is None
