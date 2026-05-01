"""Phase 2: Block Tests — integrate related nodes into functional blocks.

Block groupings:
- Schema Pipeline: SchemaParser + Store + SchemaRouter
- Scenario Pipeline: ScenarioGenerator + LLMRouter + ScenariosRouter
- Execution Pipeline: ExecutionEngine + Store + ExecutionRouter
- Report Pipeline: ReportGenerator + Store + ReportsRouter
- Security Block: Security + RateLimit + Auth middleware
- Storage Block: InMemoryStore + SQLiteStore (interchangeability)
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
from api_chaos_agent.core.security import create_access_token, get_current_user
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
    ErrorStatusConfig,
    LatencyConfig,
    TamperingConfig,
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


def _mock_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"data": "ok"})


MOCK_TRANSPORT = httpx.MockTransport(_mock_handler)


# ══════════════════════════════════════════════════════════════
# Block 1: Schema Pipeline (Parser → Store → retrieval)
# ══════════════════════════════════════════════════════════════


class TestSchemaPipeline:
    @pytest.mark.asyncio
    async def test_parse_and_store_in_memory(self):
        parser = SchemaParser()
        store = InMemoryStore(max_schemas=10, ttl_seconds=300)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            spec_data = {
                "openapi": "3.0.0",
                "info": {"title": "Pipeline API", "version": "1.0"},
                "paths": {
                    "/items": {
                        "get": {
                            "summary": "List items",
                            "responses": {"200": {"description": "OK"}},
                        }
                    }
                },
            }
            json.dump(spec_data, f)
            f.flush()
            try:
                api_spec = parser.parse(f.name)
                schema_id = await store.save_schema(api_spec)
                retrieved = await store.get_schema(schema_id)
                assert retrieved is not None
                assert retrieved.title == "Pipeline API"
                assert len(retrieved.endpoints) == 1
                assert retrieved.endpoints[0].path == "/items"
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_parse_and_store_sqlite(self):
        parser = SchemaParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SQLiteStore(db_path=db_path)
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
                spec_data = {
                    "openapi": "3.0.0",
                    "info": {"title": "SQLite Pipeline", "version": "2.0"},
                    "paths": {
                        "/users": {
                            "post": {
                                "summary": "Create user",
                                "responses": {"201": {"description": "Created"}},
                            }
                        }
                    },
                }
                json.dump(spec_data, f)
                f.flush()
                try:
                    api_spec = parser.parse(f.name)
                    schema_id = await store.save_schema(api_spec)
                    retrieved = await store.get_schema(schema_id)
                    assert retrieved is not None
                    assert retrieved.title == "SQLite Pipeline"
                finally:
                    os.unlink(f.name)
                    store.close()

    @pytest.mark.asyncio
    async def test_parse_petstore_and_generate_scenarios(self):
        parser = SchemaParser()
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        store = InMemoryStore(max_schemas=10, ttl_seconds=300)

        api_spec = parser.parse(str(PETSTORE_JSON))
        schema_id = await store.save_schema(api_spec)
        retrieved = await store.get_schema(schema_id)
        assert retrieved is not None

        scenarios = await generator.generate(retrieved)
        assert len(scenarios) >= 2

        for scenario in scenarios:
            sid = await store.save_scenario(scenario)
            s = await store.get_scenario(sid)
            assert s is not None


# ══════════════════════════════════════════════════════════════
# Block 2: Scenario Pipeline (Generator → LLMRouter → Store)
# ══════════════════════════════════════════════════════════════


class TestScenarioPipeline:
    @pytest.mark.asyncio
    async def test_generate_and_store_scenarios(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)
        store = InMemoryStore(max_scenarios=50, ttl_seconds=300)

        spec = APISpec(
            title="Test API",
            version="1.0",
            endpoints=[
                _make_endpoint(HttpMethod.GET, "/users"),
                _make_endpoint(HttpMethod.POST, "/users"),
                _make_endpoint(HttpMethod.DELETE, "/users/{id}"),
            ],
        )
        scenarios = await generator.generate(spec)
        assert len(scenarios) >= 3

        scenario_ids = []
        for s in scenarios:
            sid = await store.save_scenario(s)
            scenario_ids.append(sid)

        all_scenarios = await store.list_scenarios()
        assert len(all_scenarios) == len(scenarios)

    @pytest.mark.asyncio
    async def test_llm_router_enhances_scenarios(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        generator = ScenarioGenerator(llm_router=router)

        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                _make_endpoint(
                    HttpMethod.POST,
                    "/data",
                    request_body=RequestBody(
                        fields=[
                            FieldConstraint(field_name="email", field_type=FieldType.STRING),
                            FieldConstraint(field_name="count", field_type=FieldType.INTEGER),
                        ]
                    ),
                ),
            ],
        )
        scenarios = await generator.generate(spec)
        tampering = [s for s in scenarios if s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING]
        assert len(tampering) >= 1
        for t in tampering:
            assert "field_path" in t.config

    @pytest.mark.asyncio
    async def test_scenario_generation_with_llm_routing(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        result = await router.route(
            "change type of email field to integer",
            complexity=TaskComplexity.SIMPLE,
        )
        data = json.loads(result)
        assert data["mutation"] == "type_change"
        router.close()


# ══════════════════════════════════════════════════════════════
# Block 3: Execution Pipeline (Engine → Store → Results)
# ══════════════════════════════════════════════════════════════


class TestExecutionPipeline:
    @pytest.mark.asyncio
    async def test_execute_scenarios_and_store_results(self):
        store = InMemoryStore(max_executions=10, ttl_seconds=300)
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)

        scenarios = [
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
            _make_scenario(ChaosScenarioType.LATENCY, config={"delay_ms": 10}),
        ]
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 2
        assert result.completed_scenarios == 2

        exec_id = await store.save_execution(result)
        retrieved = await store.get_execution(exec_id)
        assert retrieved is not None
        assert retrieved.total_scenarios == 2

    @pytest.mark.asyncio
    async def test_execute_and_generate_report(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        report_gen = ReportGenerator()

        scenarios = [
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
            _make_scenario(ChaosScenarioType.LATENCY, config={"delay_ms": 10}),
        ]
        result = await engine.execute(scenarios)
        report = report_gen.generate(result)
        assert report.summary.total_scenarios == 2

    @pytest.mark.asyncio
    async def test_full_execution_pipeline_with_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SQLiteStore(db_path=db_path)
            config = ExecutionConfig(base_url="http://testserver", concurrency=2, timeout_seconds=5.0)
            engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)

            scenarios = [
                _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
                _make_scenario(ChaosScenarioType.LATENCY, config={"delay_ms": 10}),
                _make_scenario(ChaosScenarioType.RATE_LIMIT, config={"requests_per_second": 2, "duration_seconds": 1}),
            ]
            result = await engine.execute(scenarios)
            exec_id = await store.save_execution(result)
            retrieved = await store.get_execution(exec_id)
            assert retrieved is not None
            assert retrieved.total_scenarios == 3
            store.close()

    @pytest.mark.asyncio
    async def test_vulnerability_detection_pipeline(self):
        class ErrorTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return httpx.Response(500, json={"error": "internal server error"})

        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=ErrorTransport())
        report_gen = ReportGenerator()

        scenarios = [
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
        ]
        result = await engine.execute(scenarios)
        report = report_gen.generate(result)
        assert report.summary.failed >= 1
        assert len(report.findings) >= 1
        assert report.findings[0].severity in (Severity.HIGH, Severity.CRITICAL, Severity.MEDIUM)


# ══════════════════════════════════════════════════════════════
# Block 4: Report Pipeline (Generator → Store → Retrieval)
# ══════════════════════════════════════════════════════════════


class TestReportPipeline:
    @pytest.mark.asyncio
    async def test_generate_and_store_report(self):
        store = InMemoryStore(max_reports=10, ttl_seconds=300)
        report_gen = ReportGenerator()

        tr = TestResult(
            total_scenarios=2,
            results=[
                ScenarioResult(
                    scenario_id="s1",
                    scenario_name="Error Test",
                    scenario_type="error_status",
                    vulnerability_found=True,
                    severity=Severity.HIGH,
                    details="Server error",
                ),
                ScenarioResult(
                    scenario_id="s2",
                    scenario_name="Latency Test",
                    scenario_type="latency",
                    vulnerability_found=False,
                    severity=Severity.INFO,
                    details="Normal latency",
                ),
            ],
        )
        tr.completed_scenarios = 2
        report = report_gen.generate(tr)
        report_id = await store.save_report(report)
        retrieved = await store.get_report(report_id)
        assert retrieved is not None
        assert retrieved.summary.failed == 1
        assert len(retrieved.findings) == 1

    @pytest.mark.asyncio
    async def test_report_with_sqlite_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SQLiteStore(db_path=db_path)
            report_gen = ReportGenerator()

            tr = TestResult(total_scenarios=0)
            report = report_gen.generate(tr)
            report_id = await store.save_report(report)
            retrieved = await store.get_report(report_id)
            assert retrieved is not None
            assert retrieved.summary.total_scenarios == 0
            store.close()

    @pytest.mark.asyncio
    async def test_severity_aggregation_in_report(self):
        report_gen = ReportGenerator()
        tr = TestResult(
            total_scenarios=3,
            results=[
                ScenarioResult(
                    scenario_id="s1",
                    scenario_name="Critical",
                    scenario_type="error_status",
                    vulnerability_found=True,
                    severity=Severity.CRITICAL,
                    details="Critical issue",
                ),
                ScenarioResult(
                    scenario_id="s2",
                    scenario_name="High",
                    scenario_type="error_status",
                    vulnerability_found=True,
                    severity=Severity.HIGH,
                    details="High issue",
                ),
                ScenarioResult(
                    scenario_id="s3",
                    scenario_name="Medium",
                    scenario_type="latency",
                    vulnerability_found=True,
                    severity=Severity.MEDIUM,
                    details="Medium issue",
                ),
            ],
        )
        report = report_gen.generate(tr)
        assert report.summary.severity_counts.get("critical", 0) == 1
        assert report.summary.severity_counts.get("high", 0) == 1
        assert report.summary.severity_counts.get("medium", 0) == 1


# ══════════════════════════════════════════════════════════════
# Block 5: Security Block (Auth + RateLimit)
# ══════════════════════════════════════════════════════════════


class TestSecurityBlock:
    def test_token_creation_and_verification(self):
        token = create_access_token(subject="testuser")
        from api_chaos_agent.core.security import _decode_token

        payload = _decode_token(token)
        assert payload["sub"] == "testuser"

    @pytest.mark.asyncio
    async def test_auth_disabled_allows_anonymous(self):
        original = settings.auth.enabled
        try:
            object.__setattr__(settings.auth, "enabled", False)
            result = await get_current_user(None)
            assert result["sub"] == "anonymous"
        finally:
            object.__setattr__(settings.auth, "enabled", original)

    @pytest.mark.asyncio
    async def test_auth_enabled_blocks_no_token(self):
        from api_chaos_agent.core.exceptions import AuthenticationError

        original = settings.auth.enabled
        try:
            object.__setattr__(settings.auth, "enabled", True)
            with pytest.raises(AuthenticationError):
                await get_current_user(None)
        finally:
            object.__setattr__(settings.auth, "enabled", original)

    @pytest.mark.asyncio
    async def test_auth_enabled_accepts_valid_token(self):
        from fastapi.security import HTTPAuthorizationCredentials

        original = settings.auth.enabled
        try:
            object.__setattr__(settings.auth, "enabled", True)
            token = create_access_token(subject="admin")
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            result = await get_current_user(creds)
            assert result["sub"] == "admin"
        finally:
            object.__setattr__(settings.auth, "enabled", original)

    def test_rate_limit_token_bucket(self):
        from api_chaos_agent.core.rate_limit import _TokenBucket

        bucket = _TokenBucket(max_tokens=10.0, refill_rate=1.0)
        now = time.monotonic()
        for _ in range(10):
            assert bucket.consume(now) is True
        assert bucket.consume(now) is False

    def test_rate_limit_token_refill(self):
        from api_chaos_agent.core.rate_limit import _TokenBucket

        bucket = _TokenBucket(max_tokens=3.0, refill_rate=60.0)
        now = time.monotonic()
        for _ in range(3):
            bucket.consume(now)
        assert bucket.consume(now) is False
        later = now + 1.0
        assert bucket.consume(later) is True


# ══════════════════════════════════════════════════════════════
# Block 6: Storage Interchangeability (InMemory ↔ SQLite)
# ══════════════════════════════════════════════════════════════


class TestStorageInterchangeability:
    @pytest.mark.asyncio
    async def test_both_stores_save_and_retrieve_schema(self):
        mem_store = InMemoryStore(max_schemas=10, ttl_seconds=300)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sql_store = SQLiteStore(db_path=db_path)

            spec = APISpec(title="Interchange Test", version="1.0")

            mem_id = await mem_store.save_schema(spec)
            sql_id = await sql_store.save_schema(spec)

            mem_result = await mem_store.get_schema(mem_id)
            sql_result = await sql_store.get_schema(sql_id)

            assert mem_result is not None
            assert sql_result is not None
            assert mem_result.title == sql_result.title
            sql_store.close()

    @pytest.mark.asyncio
    async def test_both_stores_save_and_retrieve_scenario(self):
        mem_store = InMemoryStore(max_scenarios=10, ttl_seconds=300)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sql_store = SQLiteStore(db_path=db_path)

            scenario = _make_scenario()

            mem_id = await mem_store.save_scenario(scenario)
            sql_id = await sql_store.save_scenario(scenario)

            mem_result = await mem_store.get_scenario(mem_id)
            sql_result = await sql_store.get_scenario(sql_id)

            assert mem_result is not None
            assert sql_result is not None
            assert mem_result.name == sql_result.name
            sql_store.close()

    @pytest.mark.asyncio
    async def test_both_stores_stats(self):
        mem_store = InMemoryStore(max_schemas=10, ttl_seconds=300)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sql_store = SQLiteStore(db_path=db_path)

            await mem_store.save_schema(APISpec(title="T", version="1"))
            await sql_store.save_schema(APISpec(title="T", version="1"))

            mem_stats = await mem_store.stats()
            sql_stats = await sql_store.stats()

            assert mem_stats["schemas"] == 1
            assert sql_stats["schemas"] == 1
            sql_store.close()

    @pytest.mark.asyncio
    async def test_both_stores_clear(self):
        mem_store = InMemoryStore(max_schemas=10, ttl_seconds=300)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sql_store = SQLiteStore(db_path=db_path)

            await mem_store.save_schema(APISpec(title="T", version="1"))
            await sql_store.save_schema(APISpec(title="T", version="1"))

            await mem_store.clear()
            await sql_store.clear()

            mem_stats = await mem_store.stats()
            sql_stats = await sql_store.stats()

            assert mem_stats["schemas"] == 0
            assert sql_stats["schemas"] == 0
            sql_store.close()
