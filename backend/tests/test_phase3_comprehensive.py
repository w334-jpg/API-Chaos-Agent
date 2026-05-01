"""Phase 3: Comprehensive End-to-End Tests.

Full pipeline tests covering the complete workflow:
1. Upload OpenAPI spec → Parse → Store
2. Generate scenarios from spec
3. Execute scenarios against target
4. Generate report from results
5. Store and retrieve report

Must pass 5 consecutive rounds with zero errors and zero warnings.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile
import time

import httpx
import pytest
import pytest_asyncio

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.security import create_access_token, _decode_token
from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    Report,
    ResponseData,
    ScenarioResult,
    Severity,
    TestResult,
)
from api_chaos_agent.models.scenario import (
    ChaosScenario,
    ChaosScenarioType,
)
from api_chaos_agent.models.schema import (
    APISpec,
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    RequestBody,
)
from api_chaos_agent.models.schema import (
    APISpec,
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    RequestBody,
)
from api_chaos_agent.services.execution_engine import ExecutionEngine
from api_chaos_agent.services.llm_router import LLMRouter, TaskComplexity
from api_chaos_agent.services.report_generator import ReportGenerator
from api_chaos_agent.services.scenario_generator import ScenarioGenerator
from api_chaos_agent.services.schema_parser import SchemaParser
from api_chaos_agent.services.sqlite_store import SQLiteStore
from api_chaos_agent.services.store import InMemoryStore

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PETSTORE_JSON = FIXTURES_DIR / "petstore_openapi.json"


def _make_endpoint(
    method: HttpMethod = HttpMethod.GET,
    path: str = "/test",
    **kwargs,
) -> Endpoint:
    return Endpoint(method=method, path=path, **kwargs)


def _make_scenario(
    scenario_type: ChaosScenarioType = ChaosScenarioType.ERROR_STATUS,
    config: dict | None = None,
    **kwargs,
) -> ChaosScenario:
    endpoint = kwargs.pop("endpoint", None) or _make_endpoint()
    return ChaosScenario(
        name=kwargs.pop("name", "Test Scenario"),
        scenario_type=scenario_type,
        endpoint=endpoint,
        config=config or {},
        **kwargs,
    )


class _MultiResponseTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: dict[str, int] | None = None):
        self._responses = responses or {"default": 200}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        status = self._responses.get(path, self._responses.get("default", 200))
        return httpx.Response(status, json={"path": path, "status": status})


class _ErrorTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal server error"})


class _MixedTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"data": "ok"})
        if request.method == "POST":
            return httpx.Response(201, json={"id": 1})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"status": "ok"})


async def _run_full_pipeline(
    store_impl: str = "memory",
    transport: httpx.AsyncBaseTransport | None = None,
    spec_source: str = "petstore",
) -> dict:
    if store_impl == "sqlite":
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "pipeline.db")
        store = SQLiteStore(db_path=db_path)
    else:
        store = InMemoryStore(max_schemas=100, max_scenarios=100, max_executions=100, max_reports=100, ttl_seconds=300)
        tmpdir = None

    try:
        parser = SchemaParser()
        if spec_source == "petstore":
            api_spec = parser.parse(str(PETSTORE_JSON))
        else:
            api_spec = APISpec(
                title="Custom API",
                version="1.0",
                endpoints=[
                    _make_endpoint(HttpMethod.GET, "/users"),
                    _make_endpoint(HttpMethod.POST, "/users"),
                    _make_endpoint(HttpMethod.GET, "/users/{id}"),
                    _make_endpoint(HttpMethod.DELETE, "/users/{id}"),
                ],
            )

        schema_id = await store.save_schema(api_spec)
        retrieved_spec = await store.get_schema(schema_id)
        assert retrieved_spec is not None, "Schema retrieval failed"

        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        scenarios = await generator.generate(retrieved_spec)
        assert len(scenarios) >= 2, f"Expected >= 2 scenarios, got {len(scenarios)}"

        scenario_ids = []
        for s in scenarios:
            sid = await store.save_scenario(s)
            scenario_ids.append(sid)

        exec_config = ExecutionConfig(
            base_url="http://testserver",
            concurrency=5,
            timeout_seconds=5.0,
            max_retries=1,
        )
        actual_transport = transport or _MixedTransport()
        engine = ExecutionEngine(config=exec_config, transport=actual_transport)
        result = await engine.execute(scenarios)
        assert result.total_scenarios == len(scenarios), "Scenario count mismatch"

        exec_id = await store.save_execution(result)
        retrieved_exec = await store.get_execution(exec_id)
        assert retrieved_exec is not None, "Execution retrieval failed"

        report_gen = ReportGenerator()
        report = report_gen.generate(result)
        assert report.summary.total_scenarios == len(scenarios), "Report scenario count mismatch"

        report_id = await store.save_report(report)
        retrieved_report = await store.get_report(report_id)
        assert retrieved_report is not None, "Report retrieval failed"

        stats = await store.stats()
        assert stats["schemas"] >= 1, "No schemas in store"
        assert stats["scenarios"] >= 2, "Not enough scenarios in store"
        assert stats["executions"] >= 1, "No executions in store"
        assert stats["reports"] >= 1, "No reports in store"

        router.close()

        return {
            "schema_id": schema_id,
            "scenario_count": len(scenarios),
            "exec_id": exec_id,
            "report_id": report_id,
            "vulnerabilities": report.summary.failed,
            "stats": stats,
        }
    finally:
        if store_impl == "sqlite":
            store.close()
            if tmpdir:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
# Round 1: Full pipeline with PetStore spec, InMemory store
# ══════════════════════════════════════════════════════════════


class TestComprehensiveRound1:
    @pytest.mark.asyncio
    async def test_full_pipeline_petstore_memory(self):
        result = await _run_full_pipeline(store_impl="memory", spec_source="petstore")
        assert result["scenario_count"] >= 2
        assert result["stats"]["schemas"] >= 1
        assert result["stats"]["reports"] >= 1

    @pytest.mark.asyncio
    async def test_schema_parsing_integrity(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))
        assert "Petstore" in spec.title or "petstore" in spec.title.lower()
        assert len(spec.endpoints) >= 1
        for ep in spec.endpoints:
            assert ep.path.startswith("/")
            assert isinstance(ep.method, HttpMethod)

    @pytest.mark.asyncio
    async def test_scenario_coverage(self):
        parser = SchemaParser()
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        spec = parser.parse(str(PETSTORE_JSON))
        scenarios = await generator.generate(spec)
        types = {s.scenario_type for s in scenarios}
        assert ChaosScenarioType.LATENCY in types
        assert ChaosScenarioType.ERROR_STATUS in types
        assert ChaosScenarioType.RATE_LIMIT in types
        router.close()

    @pytest.mark.asyncio
    async def test_execution_completes_all_scenarios(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=5, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=_MixedTransport())
        parser = SchemaParser()
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        spec = parser.parse(str(PETSTORE_JSON))
        scenarios = await generator.generate(spec)
        result = await engine.execute(scenarios)
        assert result.total_scenarios == len(scenarios)
        assert result.failed_scenarios == 0
        router.close()

    @pytest.mark.asyncio
    async def test_report_generation_accuracy(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=5, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=_MixedTransport())
        report_gen = ReportGenerator()
        parser = SchemaParser()
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        spec = parser.parse(str(PETSTORE_JSON))
        scenarios = await generator.generate(spec)
        result = await engine.execute(scenarios)
        report = report_gen.generate(result)
        assert report.summary.total_scenarios == len(scenarios)
        router.close()


# ══════════════════════════════════════════════════════════════
# Round 2: Full pipeline with SQLite store
# ══════════════════════════════════════════════════════════════


class TestComprehensiveRound2:
    @pytest.mark.asyncio
    async def test_full_pipeline_sqlite(self):
        result = await _run_full_pipeline(store_impl="sqlite", spec_source="petstore")
        assert result["scenario_count"] >= 2
        assert result["stats"]["schemas"] >= 1

    @pytest.mark.asyncio
    async def test_sqlite_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "persist.db")
            store1 = SQLiteStore(db_path=db_path)
            spec = APISpec(title="Persist Test", version="1.0")
            sid = await store1.save_schema(spec)
            store1.close()

            store2 = SQLiteStore(db_path=db_path)
            result = await store2.get_schema(sid)
            assert result is not None
            assert result.title == "Persist Test"
            store2.close()

    @pytest.mark.asyncio
    async def test_sqlite_concurrent_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "concurrent.db")
            store = SQLiteStore(db_path=db_path)

            async def write_item(i: int):
                await store.save_schema(APISpec(title=f"Spec_{i}", version="1.0"))

            await asyncio.gather(*[write_item(i) for i in range(10)])
            stats = await store.stats()
            assert stats["schemas"] == 10
            store.close()

    @pytest.mark.asyncio
    async def test_sqlite_clear_and_repopulate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "clear.db")
            store = SQLiteStore(db_path=db_path)
            await store.save_schema(APISpec(title="T1", version="1"))
            await store.save_schema(APISpec(title="T2", version="1"))
            await store.clear()
            stats = await store.stats()
            assert stats["schemas"] == 0
            await store.save_schema(APISpec(title="T3", version="1"))
            stats = await store.stats()
            assert stats["schemas"] == 1
            store.close()


# ══════════════════════════════════════════════════════════════
# Round 3: Edge cases and boundary scenarios
# ══════════════════════════════════════════════════════════════


class TestComprehensiveRound3:
    @pytest.mark.asyncio
    async def test_empty_spec(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        spec = APISpec(title="Empty", version="1.0", endpoints=[])
        scenarios = await generator.generate(spec)
        assert scenarios == []
        router.close()

    @pytest.mark.asyncio
    async def test_single_endpoint_spec(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        spec = APISpec(
            title="Single",
            version="1.0",
            endpoints=[_make_endpoint(HttpMethod.GET, "/health")],
        )
        scenarios = await generator.generate(spec)
        assert len(scenarios) >= 2
        router.close()

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        class FailTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                raise httpx.ConnectError("Connection refused")

        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0, max_retries=0)
        engine = ExecutionEngine(config=config, transport=FailTransport())
        scenarios = [_make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500})]
        result = await engine.execute(scenarios)
        assert result.failed_scenarios == 1

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        class TimeoutTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                raise httpx.ReadTimeout("Read timed out")

        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=1.0, max_retries=0)
        engine = ExecutionEngine(config=config, transport=TimeoutTransport())
        scenarios = [_make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500})]
        result = await engine.execute(scenarios)
        assert result.failed_scenarios == 1

    @pytest.mark.asyncio
    async def test_large_spec_handling(self):
        endpoints = []
        for i in range(50):
            endpoints.append(_make_endpoint(HttpMethod.GET, f"/api/resource{i}"))
            endpoints.append(_make_endpoint(HttpMethod.POST, f"/api/resource{i}"))
        spec = APISpec(title="Large API", version="1.0", endpoints=endpoints)
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        scenarios = await generator.generate(spec)
        assert len(scenarios) >= 50
        router.close()

    @pytest.mark.asyncio
    async def test_store_capacity_limits(self):
        store = InMemoryStore(max_schemas=3, ttl_seconds=300)
        for i in range(5):
            await store.save_schema(APISpec(title=f"Spec_{i}", version="1.0"))
        schemas = await store.list_schemas()
        assert len(schemas) <= 3

    @pytest.mark.asyncio
    async def test_report_with_no_vulnerabilities(self):
        report_gen = ReportGenerator()
        tr = TestResult(total_scenarios=2)
        tr.completed_scenarios = 2
        tr.results = [
            ScenarioResult(
                scenario_id="s1",
                scenario_name="Safe Test 1",
                scenario_type="latency",
                vulnerability_found=False,
            ),
            ScenarioResult(
                scenario_id="s2",
                scenario_name="Safe Test 2",
                scenario_type="error_status",
                vulnerability_found=False,
            ),
        ]
        report = report_gen.generate(tr)
        assert report.summary.failed == 0
        assert report.findings == []

    @pytest.mark.asyncio
    async def test_all_http_methods(self):
        for method in [HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH, HttpMethod.DELETE]:
            config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
            engine = ExecutionEngine(config=config, transport=_MixedTransport())
            ep = _make_endpoint(method, "/resource")
            scenario = _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}, endpoint=ep)
            result = await engine.execute([scenario])
            assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_all_tamper_types(self):
        tamper_types = ["remove", "replace", "overflow", "type_mismatch", "inject"]
        for tt in tamper_types:
            config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
            engine = ExecutionEngine(config=config, transport=_MixedTransport())
            ep = _make_endpoint(
                HttpMethod.POST,
                request_body=RequestBody(
                    fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]
                ),
            )
            cfg = {"field_path": "name", "tamper_type": tt}
            if tt == "replace":
                cfg["tamper_value"] = "REPLACED"
            elif tt == "inject":
                cfg["tamper_value"] = True
            scenario = _make_scenario(ChaosScenarioType.REQUEST_TAMPERING, config=cfg, endpoint=ep)
            result = await engine.execute([scenario])
            assert result.total_scenarios == 1


# ══════════════════════════════════════════════════════════════
# Round 4: Security and authentication integration
# ══════════════════════════════════════════════════════════════


class TestComprehensiveRound4:
    @pytest.mark.asyncio
    async def test_token_lifecycle(self):
        token = create_access_token(subject="user1")
        payload = _decode_token(token)
        assert payload["sub"] == "user1"
        assert "exp" in payload
        assert "iat" in payload

    @pytest.mark.asyncio
    async def test_different_users_different_tokens(self):
        token1 = create_access_token(subject="user1")
        token2 = create_access_token(subject="user2")
        payload1 = _decode_token(token1)
        payload2 = _decode_token(token2)
        assert payload1["sub"] != payload2["sub"]

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self):
        import datetime as _dt
        from api_chaos_agent.core.exceptions import AuthenticationError

        token = create_access_token(subject="expired_user", expires_delta=_dt.timedelta(seconds=-1))
        with pytest.raises(AuthenticationError):
            _decode_token(token)

    @pytest.mark.asyncio
    async def test_tampered_token_rejected(self):
        from api_chaos_agent.core.exceptions import AuthenticationError

        token = create_access_token(subject="user1")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(AuthenticationError):
            _decode_token(tampered)

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        from api_chaos_agent.services.llm_router import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, reset_timeout=0.1)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.is_available() is False
        time.sleep(0.15)
        assert cb.state == "half-open"
        cb.record_success()
        assert cb.state == "closed"
        assert cb.is_available() is True

    @pytest.mark.asyncio
    async def test_llm_router_caching_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            router = LLMRouter(
                config={
                    "openai_api_key": "",
                    "anthropic_api_key": "",
                    "cache_dir": tmpdir,
                    "cache_ttl": 60,
                }
            )
            result1 = await router.route("change type of name", complexity=TaskComplexity.SIMPLE)
            result2 = await router.route("change type of name", complexity=TaskComplexity.SIMPLE)
            assert result1 == result2
            router.close()

    @pytest.mark.asyncio
    async def test_full_pipeline_with_auth(self):
        original = settings.auth.enabled
        try:
            object.__setattr__(settings.auth, "enabled", True)
            token = create_access_token(subject="testadmin")
            payload = _decode_token(token)
            assert payload["sub"] == "testadmin"
        finally:
            object.__setattr__(settings.auth, "enabled", original)


# ══════════════════════════════════════════════════════════════
# Round 5: Stress and concurrency tests
# ══════════════════════════════════════════════════════════════


class TestComprehensiveRound5:
    @pytest.mark.asyncio
    async def test_concurrent_pipeline_executions(self):
        store = InMemoryStore(max_schemas=100, max_scenarios=100, max_executions=100, max_reports=100, ttl_seconds=300)
        config = ExecutionConfig(base_url="http://testserver", concurrency=10, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=_MixedTransport())

        async def run_single_pipeline(i: int):
            spec = APISpec(title=f"Concurrent_{i}", version="1.0", endpoints=[_make_endpoint(HttpMethod.GET, f"/api/{i}")])
            sid = await store.save_schema(spec)
            router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
            generator = ScenarioGenerator(llm_router=router)
            scenarios = await generator.generate(spec)
            result = await engine.execute(scenarios)
            eid = await store.save_execution(result)
            report_gen = ReportGenerator()
            report = report_gen.generate(result)
            rid = await store.save_report(report)
            router.close()
            return {"schema_id": sid, "exec_id": eid, "report_id": rid}

        results = await asyncio.gather(*[run_single_pipeline(i) for i in range(5)])
        assert len(results) == 5
        for r in results:
            assert r["schema_id"] is not None
            assert r["exec_id"] is not None
            assert r["report_id"] is not None

    @pytest.mark.asyncio
    async def test_high_concurrency_execution(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=20, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=_MixedTransport())
        scenarios = [
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}, name=f"Scenario_{i}")
            for i in range(20)
        ]
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 20
        assert result.completed_scenarios == 20

    @pytest.mark.asyncio
    async def test_rapid_store_operations(self):
        store = InMemoryStore(max_schemas=1000, ttl_seconds=300)

        async def rapid_write(i: int):
            sid = await store.save_schema(APISpec(title=f"Rapid_{i}", version="1.0"))
            retrieved = await store.get_schema(sid)
            return retrieved is not None

        results = await asyncio.gather(*[rapid_write(i) for i in range(50)])
        assert all(results)

    @pytest.mark.asyncio
    async def test_mixed_scenario_types_execution(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=5, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=_MixedTransport())

        scenarios = [
            _make_scenario(ChaosScenarioType.LATENCY, config={"delay_ms": 10}),
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
            _make_scenario(
                ChaosScenarioType.REQUEST_TAMPERING,
                config={"field_path": "name", "tamper_type": "remove"},
                endpoint=_make_endpoint(
                    HttpMethod.POST,
                    request_body=RequestBody(fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]),
                ),
            ),
            _make_scenario(ChaosScenarioType.RATE_LIMIT, config={"requests_per_second": 5, "duration_seconds": 1}),
        ]
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 4

    @pytest.mark.asyncio
    async def test_full_pipeline_custom_spec(self):
        result = await _run_full_pipeline(store_impl="memory", spec_source="custom")
        assert result["scenario_count"] >= 2
        assert result["stats"]["schemas"] >= 1
        assert result["stats"]["reports"] >= 1

    @pytest.mark.asyncio
    async def test_pipeline_with_error_transport(self):
        result = await _run_full_pipeline(store_impl="memory", transport=_ErrorTransport(), spec_source="custom")
        assert result["vulnerabilities"] >= 1
