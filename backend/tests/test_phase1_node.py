"""Phase 1: Node Tests — verify each independent module, interface, and component.

Tests are organized by module:
- 1.1 Models (schema, scenario, report)
- 1.2 Core (config, security, rate_limit, logging)
- 1.3 Services (store, sqlite_store, execution_engine, schema_parser,
                scenario_generator, report_generator, llm_router)
- 1.4 Routers (schema, scenarios, execution, reports)
- 1.5 Main app (middleware, health checks, auth, websocket)
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

from api_chaos_agent.core.config import (
    AppConfig,
    AuthConfig,
    LLMConfig,
    LoggingConfig,
    RateLimitConfig,
    ServerConfig,
    StoreConfig,
    settings,
)
from api_chaos_agent.core.config import (
    ExecutionConfig as CoreExecutionConfig,
)
from api_chaos_agent.core.logging import get_logger, setup_logging
from api_chaos_agent.core.rate_limit import _TokenBucket
from api_chaos_agent.core.security import (
    _decode_token,
    create_access_token,
    get_current_user,
)
from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    Finding,
    Report,
    ReportSummary,
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
from api_chaos_agent.models.scenario import (
    RateLimitConfig as ScenarioRateLimitConfig,
)
from api_chaos_agent.models.schema import (
    APISpec,
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    Parameter,
    RequestBody,
    ResponseSpec,
)
from api_chaos_agent.services.execution_engine import ExecutionEngine
from api_chaos_agent.services.llm_router import (
    CircuitBreaker,
    LLMRouter,
    TaskComplexity,
)
from api_chaos_agent.services.report_generator import ReportGenerator
from api_chaos_agent.services.scenario_generator import ScenarioGenerator
from api_chaos_agent.services.schema_parser import SchemaParser
from api_chaos_agent.services.sqlite_store import SQLiteStore
from api_chaos_agent.services.store import InMemoryStore

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PETSTORE_JSON = FIXTURES_DIR / "petstore_openapi.json"
PETSTORE_YAML = FIXTURES_DIR / "petstore_openapi.yaml"


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
    if request.method == "GET":
        return httpx.Response(200, json={"data": "ok"})
    if request.method == "POST":
        return httpx.Response(201, json={"id": 1, "created": True})
    if request.method == "DELETE":
        return httpx.Response(204)
    if request.method == "PUT":
        return httpx.Response(200, json={"updated": True})
    if request.method == "PATCH":
        return httpx.Response(200, json={"patched": True})
    return httpx.Response(200, json={"status": "ok"})


MOCK_TRANSPORT = httpx.MockTransport(_mock_handler)


# ══════════════════════════════════════════════════════════════
# 1.1 Models — Schema Model
# ══════════════════════════════════════════════════════════════


class TestSchemaModels:
    def test_http_method_enum_values(self):
        assert HttpMethod.GET.value == "GET"
        assert HttpMethod.POST.value == "POST"
        assert HttpMethod.PUT.value == "PUT"
        assert HttpMethod.PATCH.value == "PATCH"
        assert HttpMethod.DELETE.value == "DELETE"
        assert HttpMethod.HEAD.value == "HEAD"
        assert HttpMethod.OPTIONS.value == "OPTIONS"

    def test_field_type_enum_values(self):
        assert FieldType.STRING.value == "string"
        assert FieldType.INTEGER.value == "integer"
        assert FieldType.NUMBER.value == "number"
        assert FieldType.BOOLEAN.value == "boolean"
        assert FieldType.ARRAY.value == "array"
        assert FieldType.OBJECT.value == "object"
        assert FieldType.NULL.value == "null"

    def test_field_constraint_defaults(self):
        fc = FieldConstraint(field_name="test", field_type=FieldType.STRING)
        assert fc.required is False
        assert fc.min_length is None
        assert fc.max_length is None
        assert fc.minimum is None
        assert fc.maximum is None
        assert fc.pattern is None
        assert fc.format is None
        assert fc.enum_values is None
        assert fc.default is None

    def test_field_constraint_all_fields(self):
        fc = FieldConstraint(
            field_name="age",
            field_type=FieldType.INTEGER,
            required=True,
            minimum=0,
            maximum=150,
        )
        assert fc.required is True
        assert fc.minimum == 0
        assert fc.maximum == 150

    def test_parameter_model(self):
        p = Parameter(
            name="id",
            location="path",
            param_type=FieldType.STRING,
            required=True,
            description="Resource ID",
        )
        assert p.name == "id"
        assert p.location == "path"
        assert p.required is True

    def test_request_body_model(self):
        rb = RequestBody(
            content_type="application/json",
            required=True,
            fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING, required=True)],
        )
        assert rb.content_type == "application/json"
        assert rb.required is True
        assert len(rb.fields) == 1

    def test_response_spec_model(self):
        rs = ResponseSpec(status_code="200", description="Success")
        assert rs.status_code == "200"
        assert rs.content_type is None
        assert rs.schema_ref is None

    def test_endpoint_model(self):
        ep = Endpoint(
            path="/users",
            method=HttpMethod.GET,
            summary="List users",
            tags=["users"],
        )
        assert ep.path == "/users"
        assert ep.method == HttpMethod.GET
        assert ep.parameters == []
        assert ep.request_body is None
        assert ep.responses == []
        assert ep.tags == ["users"]
        assert ep.operation_id is None

    def test_api_spec_model(self):
        spec = APISpec(
            title="Test API",
            version="1.0.0",
            description="A test API",
            base_url="http://localhost:8000",
        )
        assert spec.title == "Test API"
        assert spec.version == "1.0.0"
        assert spec.endpoints == []
        assert spec.raw_spec == {}

    def test_api_spec_serialization(self):
        spec = APISpec(title="Test", version="2.0")
        data = spec.model_dump_json()
        restored = APISpec.model_validate_json(data)
        assert restored.title == "Test"
        assert restored.version == "2.0"


# ══════════════════════════════════════════════════════════════
# 1.1 Models — Scenario Model
# ══════════════════════════════════════════════════════════════


class TestScenarioModels:
    def test_chaos_scenario_type_enum(self):
        assert ChaosScenarioType.LATENCY.value == "latency"
        assert ChaosScenarioType.ERROR_STATUS.value == "error_status"
        assert ChaosScenarioType.REQUEST_TAMPERING.value == "request_tampering"
        assert ChaosScenarioType.RATE_LIMIT.value == "rate_limit"

    def test_severity_enum(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"

    def test_latency_config_validation(self):
        lc = LatencyConfig(delay_ms=1000, jitter_ms=100)
        assert lc.delay_ms == 1000
        assert lc.jitter_ms == 100

    def test_latency_config_rejects_negative(self):
        with pytest.raises(Exception):
            LatencyConfig(delay_ms=-1)

    def test_error_status_config_validation(self):
        ec = ErrorStatusConfig(status_code=500, repeat_count=3)
        assert ec.status_code == 500
        assert ec.repeat_count == 3

    def test_error_status_config_range(self):
        with pytest.raises(Exception):
            ErrorStatusConfig(status_code=99)
        with pytest.raises(Exception):
            ErrorStatusConfig(status_code=600)

    def test_tampering_config(self):
        tc = TamperingConfig(field_path="name", tamper_type="remove")
        assert tc.field_path == "name"
        assert tc.tamper_type == "remove"

    def test_rate_limit_config(self):
        rc = ScenarioRateLimitConfig(requests_per_second=100, duration_seconds=5)
        assert rc.requests_per_second == 100
        assert rc.duration_seconds == 5

    def test_rate_limit_config_rejects_zero(self):
        with pytest.raises(Exception):
            ScenarioRateLimitConfig(requests_per_second=0)

    def test_chaos_scenario_model(self):
        scenario = _make_scenario()
        assert scenario.name == "Test Scenario"
        assert scenario.scenario_type == ChaosScenarioType.ERROR_STATUS
        assert scenario.severity == Severity.MEDIUM

    def test_chaos_scenario_default_id_is_empty(self):
        scenario = _make_scenario()
        assert scenario.id == ""


# ══════════════════════════════════════════════════════════════
# 1.1 Models — Report Model
# ══════════════════════════════════════════════════════════════


class TestReportModels:
    def test_execution_status_enum(self):
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.TIMEOUT.value == "timeout"

    def test_execution_config_defaults(self):
        ec = ExecutionConfig(base_url="http://test")
        assert ec.concurrency == 10
        assert ec.timeout_seconds == 30.0
        assert ec.max_retries == 2
        assert ec.retry_delay_seconds == 1.0
        assert ec.headers == {}
        assert ec.proxy is None
        assert ec.serial is False

    def test_execution_config_validation(self):
        with pytest.raises(Exception):
            ExecutionConfig(base_url="http://test", concurrency=0)
        with pytest.raises(Exception):
            ExecutionConfig(base_url="http://test", concurrency=1001)
        with pytest.raises(Exception):
            ExecutionConfig(base_url="http://test", timeout_seconds=0.5)
        with pytest.raises(Exception):
            ExecutionConfig(base_url="http://test", max_retries=-1)
        with pytest.raises(Exception):
            ExecutionConfig(base_url="http://test", max_retries=11)

    def test_response_data_defaults(self):
        rd = ResponseData()
        assert rd.status_code is None
        assert rd.headers == {}
        assert rd.body is None
        assert rd.elapsed_ms == 0.0
        assert rd.error is None

    def test_scenario_result_model(self):
        sr = ScenarioResult(
            scenario_id="s1",
            scenario_name="Test",
            scenario_type="latency",
        )
        assert sr.status == ExecutionStatus.PENDING
        assert sr.vulnerability_found is False

    def test_test_result_model(self):
        tr = TestResult()
        assert tr.total_scenarios == 0
        assert tr.completed_scenarios == 0
        assert tr.failed_scenarios == 0
        assert tr.results == []
        assert tr.config is None
        assert tr.__test__ is False

    def test_finding_model(self):
        f = Finding(
            scenario_id="s1",
            scenario_name="Test",
            scenario_type="latency",
            endpoint_path="/test",
            endpoint_method="GET",
            severity=Severity.HIGH,
            vulnerability_found=True,
            details="Test finding",
        )
        assert f.vulnerability_found is True
        assert f.recommendation == ""

    def test_report_model(self):
        r = Report(id="test", schema_id="test", summary=ReportSummary())
        assert r.summary.total_scenarios == 0
        assert r.summary.failed == 0
        assert r.summary.severity_counts == {}
        assert r.findings == []

    def test_execution_config_serialization(self):
        ec = ExecutionConfig(base_url="http://test", concurrency=5, timeout_seconds=10.0)
        data = ec.model_dump_json()
        restored = ExecutionConfig.model_validate_json(data)
        assert restored.base_url == "http://test"
        assert restored.concurrency == 5


# ══════════════════════════════════════════════════════════════
# 1.2 Core — Config
# ══════════════════════════════════════════════════════════════


class TestConfig:
    def test_default_settings(self):
        assert settings.store.max_schemas == 1000
        assert settings.store.ttl_seconds == 3600.0
        assert settings.store.backend == "memory"
        assert settings.auth.enabled is False
        assert isinstance(settings.rate_limit.enabled, bool)
        assert settings.rate_limit.requests_per_minute == 60
        assert settings.logging.level == "INFO"

    def test_store_config_custom(self):
        cfg = StoreConfig(max_schemas=50, ttl_seconds=60.0, backend="sqlite")
        assert cfg.max_schemas == 50
        assert cfg.ttl_seconds == 60.0
        assert cfg.backend == "sqlite"

    def test_execution_config_custom(self):
        cfg = CoreExecutionConfig(max_burst_requests=100, backoff_base=2.0)
        assert cfg.max_burst_requests == 100
        assert cfg.backoff_base == 2.0

    def test_llm_config_custom(self):
        cfg = LLMConfig(openai_api_key="test-key", openai_model="gpt-4")
        assert cfg.openai_api_key == "test-key"
        assert cfg.openai_model == "gpt-4"

    def test_server_config_custom(self):
        cfg = ServerConfig(host="127.0.0.1", port=9000)
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9000

    def test_auth_config_custom(self):
        cfg = AuthConfig(enabled=True, secret_key="my-secret")
        assert cfg.enabled is True
        assert cfg.secret_key == "my-secret"

    def test_rate_limit_config_custom(self):
        cfg = RateLimitConfig(enabled=False, requests_per_minute=120)
        assert cfg.enabled is False
        assert cfg.requests_per_minute == 120

    def test_logging_config_custom(self):
        cfg = LoggingConfig(level="DEBUG", format="json")
        assert cfg.level == "DEBUG"
        assert cfg.format == "json"

    def test_app_config_composition(self):
        cfg = AppConfig()
        assert isinstance(cfg.store, StoreConfig)
        assert isinstance(cfg.execution, CoreExecutionConfig)
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.server, ServerConfig)
        assert isinstance(cfg.auth, AuthConfig)
        assert isinstance(cfg.rate_limit, RateLimitConfig)
        assert isinstance(cfg.logging, LoggingConfig)

    def test_config_frozen(self):
        cfg = StoreConfig()
        with pytest.raises(Exception):
            cfg.max_schemas = 999


# ══════════════════════════════════════════════════════════════
# 1.2 Core — Security
# ══════════════════════════════════════════════════════════════


class TestSecurity:
    def test_create_access_token(self):
        token = create_access_token(subject="testuser")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        token = create_access_token(subject="testuser")
        payload = _decode_token(token)
        assert payload["sub"] == "testuser"
        assert "exp" in payload
        assert "iat" in payload

    def test_decode_expired_token(self):
        import datetime as _dt

        token = create_access_token(
            subject="testuser",
            expires_delta=_dt.timedelta(seconds=-1),
        )
        from api_chaos_agent.core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError) as exc_info:
            _decode_token(token)
        assert "expired" in exc_info.value.detail.lower()

    def test_decode_invalid_token(self):
        from api_chaos_agent.core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError) as exc_info:
            _decode_token("invalid.token.here")
        assert "invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_auth_disabled(self):

        try:
            if hasattr(settings.auth, "enabled"):
                pass
            result = await get_current_user(None)
            assert result["sub"] == "anonymous"
        finally:
            pass

    @pytest.mark.asyncio
    async def test_get_current_user_auth_enabled_no_token(self):
        from api_chaos_agent.core.exceptions import AuthenticationError

        original = settings.auth.enabled
        try:
            object.__setattr__(settings.auth, "enabled", True)
            with pytest.raises(AuthenticationError):
                await get_current_user(None)
        finally:
            object.__setattr__(settings.auth, "enabled", original)


# ══════════════════════════════════════════════════════════════
# 1.2 Core — Rate Limit
# ══════════════════════════════════════════════════════════════


class TestRateLimit:
    def test_token_bucket_consume(self):
        b = _TokenBucket(max_tokens=10.0, refill_rate=1.0)
        now = time.monotonic()
        assert b.consume(now) is True

    def test_token_bucket_multiple_consumes(self):
        b = _TokenBucket(max_tokens=5.0, refill_rate=1.0)
        now = time.monotonic()
        for _ in range(5):
            assert b.consume(now) is True
        assert b.consume(now) is False

    def test_token_bucket_refill(self):
        b = _TokenBucket(max_tokens=5.0, refill_rate=60.0)
        now = time.monotonic()
        for _ in range(5):
            b.consume(now)
        assert b.consume(now) is False
        later = now + 1.0
        assert b.consume(later) is True


# ══════════════════════════════════════════════════════════════
# 1.2 Core — Logging
# ══════════════════════════════════════════════════════════════


class TestLogging:
    def test_setup_logging(self):
        setup_logging()
        import logging

        root = logging.getLogger()
        assert len(root.handlers) > 0

    def test_get_logger(self):
        logger = get_logger("test_module")
        assert logger is not None

    def test_setup_logging_json_format(self):
        original = os.environ.get("LOG_FORMAT")
        os.environ["LOG_FORMAT"] = "json"
        try:
            from api_chaos_agent.core.config import LoggingConfig as _LC

            cfg = _LC(format="json")
            assert cfg.format == "json"
        finally:
            if original is None:
                os.environ.pop("LOG_FORMAT", None)
            else:
                os.environ["LOG_FORMAT"] = original


# ══════════════════════════════════════════════════════════════
# 1.3 Services — InMemoryStore
# ══════════════════════════════════════════════════════════════


class TestInMemoryStore:
    @pytest.mark.asyncio
    async def test_save_and_get_schema(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        spec = APISpec(title="Test", version="1.0")
        sid = await s.save_schema(spec)
        result = await s.get_schema(sid)
        assert result is not None
        assert result.title == "Test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_schema(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        result = await s.get_schema("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_schemas(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        await s.save_schema(APISpec(title="A", version="1"))
        await s.save_schema(APISpec(title="B", version="2"))
        schemas = await s.list_schemas()
        assert len(schemas) == 2

    @pytest.mark.asyncio
    async def test_save_and_get_scenario(self):
        s = InMemoryStore(max_scenarios=10, ttl_seconds=300)
        scenario = _make_scenario()
        sid = await s.save_scenario(scenario)
        result = await s.get_scenario(sid)
        assert result is not None
        assert result.name == "Test Scenario"

    @pytest.mark.asyncio
    async def test_save_and_get_execution(self):
        s = InMemoryStore(max_executions=10, ttl_seconds=300)
        tr = TestResult(total_scenarios=1)
        eid = await s.save_execution(tr)
        result = await s.get_execution(eid)
        assert result is not None
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_save_and_get_report(self):
        s = InMemoryStore(max_reports=10, ttl_seconds=300)
        report = Report(id="test", schema_id="test", summary=ReportSummary())
        rid = await s.save_report(report)
        result = await s.get_report(rid)
        assert result is not None
        assert result.id == "test"

    @pytest.mark.asyncio
    async def test_stats(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        await s.save_schema(APISpec(title="T", version="1"))
        stats = await s.stats()
        assert stats["schemas"] == 1
        assert stats["scenarios"] == 0

    @pytest.mark.asyncio
    async def test_clear(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        await s.save_schema(APISpec(title="T", version="1"))
        await s.clear()
        stats = await s.stats()
        assert stats["schemas"] == 0

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=0.05)
        spec = APISpec(title="Expiring", version="1.0")
        schema_id = await s.save_schema(spec)
        await asyncio.sleep(0.1)
        result = await s.get_schema(schema_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        s = InMemoryStore(max_schemas=2, ttl_seconds=300)
        await s.save_schema(APISpec(title="A", version="1"))
        await s.save_schema(APISpec(title="B", version="1"))
        await s.save_schema(APISpec(title="C", version="1"))
        schemas = await s.list_schemas()
        assert len(schemas) <= 2

    @pytest.mark.asyncio
    async def test_concurrent_writes(self):
        s = InMemoryStore(max_schemas=100, ttl_seconds=300)

        async def write_schema(i: int):
            await s.save_schema(APISpec(title=f"Schema_{i}", version="1"))

        await asyncio.gather(*[write_schema(i) for i in range(20)])
        schemas = await s.list_schemas()
        assert len(schemas) == 20

    @pytest.mark.asyncio
    async def test_deterministic_id_same_spec(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        spec = APISpec(title="SameTitle", version="1.0")
        id1 = await s.save_schema(spec)
        id2 = await s.save_schema(spec)
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_unique_id_different_spec(self):
        s = InMemoryStore(max_schemas=10, ttl_seconds=300)
        id1 = await s.save_schema(APISpec(title="TitleA", version="1.0"))
        id2 = await s.save_schema(APISpec(title="TitleB", version="1.0"))
        assert id1 != id2


# ══════════════════════════════════════════════════════════════
# 1.3 Services — SQLiteStore
# ══════════════════════════════════════════════════════════════


class TestSQLiteStore:
    @pytest.mark.asyncio
    async def test_save_and_get_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            spec = APISpec(title="SQLite Test", version="1.0")
            sid = await s.save_schema(spec)
            result = await s.get_schema(sid)
            assert result is not None
            assert result.title == "SQLite Test"
            s.close()

    @pytest.mark.asyncio
    async def test_list_schemas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            await s.save_schema(APISpec(title="A", version="1"))
            await s.save_schema(APISpec(title="B", version="2"))
            schemas = await s.list_schemas()
            assert len(schemas) == 2
            s.close()

    @pytest.mark.asyncio
    async def test_save_and_get_scenario(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            scenario = _make_scenario()
            sid = await s.save_scenario(scenario)
            result = await s.get_scenario(sid)
            assert result is not None
            s.close()

    @pytest.mark.asyncio
    async def test_save_and_get_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            tr = TestResult(total_scenarios=3)
            eid = await s.save_execution(tr)
            result = await s.get_execution(eid)
            assert result is not None
            assert result.total_scenarios == 3
            s.close()

    @pytest.mark.asyncio
    async def test_save_and_get_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            report = Report(id="sqlite-test", schema_id="test", summary=ReportSummary())
            rid = await s.save_report(report)
            result = await s.get_report(rid)
            assert result is not None
            assert result.id == "sqlite-test"
            s.close()

    @pytest.mark.asyncio
    async def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            await s.save_schema(APISpec(title="T", version="1"))
            stats = await s.stats()
            assert stats["schemas"] == 1
            s.close()

    @pytest.mark.asyncio
    async def test_clear(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            await s.save_schema(APISpec(title="T", version="1"))
            await s.clear()
            stats = await s.stats()
            assert stats["schemas"] == 0
            s.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            s = SQLiteStore(db_path=db_path)
            result = await s.get_schema("nonexistent")
            assert result is None
            s.close()

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "persist.db")
            s1 = SQLiteStore(db_path=db_path)
            spec = APISpec(title="Persistent", version="1.0")
            sid = await s1.save_schema(spec)
            s1.close()

            s2 = SQLiteStore(db_path=db_path)
            result = await s2.get_schema(sid)
            assert result is not None
            assert result.title == "Persistent"
            s2.close()


# ══════════════════════════════════════════════════════════════
# 1.3 Services — ExecutionEngine
# ══════════════════════════════════════════════════════════════


class TestExecutionEngine:
    @pytest.mark.asyncio
    async def test_latency_injection(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        scenario = _make_scenario(
            ChaosScenarioType.LATENCY,
            config={"delay_ms": 10, "jitter_ms": 0},
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1
        assert result.completed_scenarios == 1

    @pytest.mark.asyncio
    async def test_error_status_scenario(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        scenario = _make_scenario(
            ChaosScenarioType.ERROR_STATUS,
            config={"status_code": 500},
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_tamper_remove_field(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]
            ),
        )
        scenario = _make_scenario(
            ChaosScenarioType.REQUEST_TAMPERING,
            config={"field_path": "name", "tamper_type": "remove"},
            endpoint=ep,
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_tamper_replace_field(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]
            ),
        )
        scenario = _make_scenario(
            ChaosScenarioType.REQUEST_TAMPERING,
            config={"field_path": "name", "tamper_type": "replace", "tamper_value": "HACKED"},
            endpoint=ep,
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_tamper_overflow(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]
            ),
        )
        scenario = _make_scenario(
            ChaosScenarioType.REQUEST_TAMPERING,
            config={"field_path": "name", "tamper_type": "overflow"},
            endpoint=ep,
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_tamper_type_mismatch(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[FieldConstraint(field_name="age", field_type=FieldType.INTEGER)]
            ),
        )
        scenario = _make_scenario(
            ChaosScenarioType.REQUEST_TAMPERING,
            config={"field_path": "age", "tamper_type": "type_mismatch"},
            endpoint=ep,
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_tamper_inject(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]
            ),
        )
        scenario = _make_scenario(
            ChaosScenarioType.REQUEST_TAMPERING,
            config={"field_path": "name", "tamper_type": "inject", "tamper_value": True},
            endpoint=ep,
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_rate_limit_burst(self):
        config = ExecutionConfig(base_url="http://testserver", concurrency=5, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        scenario = _make_scenario(
            ChaosScenarioType.RATE_LIMIT,
            config={"requests_per_second": 2, "duration_seconds": 1},
        )
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_serial_execution(self):
        config = ExecutionConfig(
            base_url="http://testserver", concurrency=1, timeout_seconds=5.0, serial=True
        )
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        scenarios = [
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 404}),
        ]
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 2

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        config = ExecutionConfig(
            base_url="http://testserver", concurrency=5, timeout_seconds=5.0, serial=False
        )
        engine = ExecutionEngine(config=config, transport=MOCK_TRANSPORT)
        scenarios = [
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500}),
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 404}),
            _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 503}),
        ]
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 3
        assert result.completed_scenarios == 3

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        class FailingTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                raise httpx.ConnectError("Connection refused")

        config = ExecutionConfig(
            base_url="http://testserver", concurrency=1, timeout_seconds=5.0, max_retries=0
        )
        engine = ExecutionEngine(config=config, transport=FailingTransport())
        scenario = _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500})
        result = await engine.execute([scenario])
        assert result.failed_scenarios == 1

    @pytest.mark.asyncio
    async def test_vulnerability_detection_error_status(self):
        class ErrorTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return httpx.Response(500, json={"error": "internal"})

        config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
        engine = ExecutionEngine(config=config, transport=ErrorTransport())
        scenario = _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500})
        result = await engine.execute([scenario])
        assert result.results[0].vulnerability_found is True

    @pytest.mark.asyncio
    async def test_build_default_body_with_fields(self):
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[
                    FieldConstraint(field_name="name", field_type=FieldType.STRING),
                    FieldConstraint(field_name="age", field_type=FieldType.INTEGER),
                    FieldConstraint(field_name="score", field_type=FieldType.NUMBER),
                    FieldConstraint(field_name="active", field_type=FieldType.BOOLEAN),
                    FieldConstraint(field_name="tags", field_type=FieldType.ARRAY),
                    FieldConstraint(field_name="meta", field_type=FieldType.OBJECT),
                ]
            ),
        )
        body = ExecutionEngine._build_default_body(ep)
        assert body["name"] == "test_string"
        assert body["age"] == 42
        assert body["score"] == 3.14
        assert body["active"] is False
        assert body["tags"] == []
        assert body["meta"] == {}

    @pytest.mark.asyncio
    async def test_build_default_body_without_fields(self):
        ep = _make_endpoint(HttpMethod.POST)
        body = ExecutionEngine._build_default_body(ep)
        assert "name" in body
        assert "id" in body


# ══════════════════════════════════════════════════════════════
# 1.3 Services — SchemaParser
# ══════════════════════════════════════════════════════════════


class TestSchemaParser:
    def test_parse_nonexistent_file(self):
        parser = SchemaParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path/spec.json")

    def test_parse_unsupported_extension(self):
        parser = SchemaParser()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(b"<spec/>")
            f.flush()
            try:
                with pytest.raises(ValueError, match="Unsupported"):
                    parser.parse(f.name)
            finally:
                os.unlink(f.name)

    def test_parse_invalid_json(self):
        parser = SchemaParser()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("{invalid json")
            f.flush()
            try:
                with pytest.raises(ValueError, match="Failed to parse"):
                    parser.parse(f.name)
            finally:
                os.unlink(f.name)

    def test_parse_missing_openapi_field(self):
        parser = SchemaParser()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"info": {"title": "Test"}}, f)
            f.flush()
            try:
                with pytest.raises(ValueError, match="missing 'openapi'"):
                    parser.parse(f.name)
            finally:
                os.unlink(f.name)

    def test_parse_valid_json_spec(self):
        parser = SchemaParser()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            spec = {
                "openapi": "3.0.0",
                "info": {"title": "Test API", "version": "1.0.0"},
                "paths": {
                    "/users": {
                        "get": {
                            "summary": "List users",
                            "responses": {"200": {"description": "OK"}},
                        }
                    }
                },
            }
            json.dump(spec, f)
            f.flush()
            try:
                result = parser.parse(f.name)
                assert result.title == "Test API"
                assert result.version == "1.0.0"
                assert len(result.endpoints) == 1
                assert result.endpoints[0].path == "/users"
                assert result.endpoints[0].method == HttpMethod.GET
            finally:
                os.unlink(f.name)

    def test_parse_valid_yaml_spec(self):
        parser = SchemaParser()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            import yaml

            spec = {
                "openapi": "3.0.0",
                "info": {"title": "YAML API", "version": "2.0.0"},
                "paths": {
                    "/items": {
                        "post": {
                            "summary": "Create item",
                            "responses": {"201": {"description": "Created"}},
                        }
                    }
                },
            }
            yaml.dump(spec, f)
            f.flush()
            try:
                result = parser.parse(f.name)
                assert result.title == "YAML API"
                assert len(result.endpoints) == 1
                assert result.endpoints[0].method == HttpMethod.POST
            finally:
                os.unlink(f.name)

    def test_infer_types_with_properties(self):
        parser = SchemaParser()
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "age": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        }
        fields = parser.infer_types(schema)
        assert len(fields) == 2
        assert fields[0].field_name == "name"
        assert fields[0].required is True
        assert fields[1].field_name == "age"
        assert fields[1].required is False

    def test_infer_types_empty_schema(self):
        parser = SchemaParser()
        fields = parser.infer_types({})
        assert fields == []

    def test_extract_base_url(self):
        result = SchemaParser._extract_base_url({"servers": [{"url": "https://api.example.com"}]})
        assert result == "https://api.example.com"

    def test_extract_base_url_no_servers(self):
        result = SchemaParser._extract_base_url({})
        assert result is None

    def test_parse_with_parameters(self):
        parser = SchemaParser()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            spec = {
                "openapi": "3.0.0",
                "info": {"title": "Param API", "version": "1.0"},
                "paths": {
                    "/users/{id}": {
                        "get": {
                            "summary": "Get user",
                            "parameters": [
                                {
                                    "name": "id",
                                    "in": "path",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            ],
                            "responses": {"200": {"description": "OK"}},
                        }
                    }
                },
            }
            json.dump(spec, f)
            f.flush()
            try:
                result = parser.parse(f.name)
                assert len(result.endpoints) == 1
                assert len(result.endpoints[0].parameters) == 1
                assert result.endpoints[0].parameters[0].name == "id"
                assert result.endpoints[0].parameters[0].location == "path"
            finally:
                os.unlink(f.name)


# ══════════════════════════════════════════════════════════════
# 1.3 Services — ScenarioGenerator
# ══════════════════════════════════════════════════════════════


class TestScenarioGenerator:
    @pytest.mark.asyncio
    async def test_generate_for_get_endpoint(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        gen = ScenarioGenerator(llm_router=router)
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[_make_endpoint(HttpMethod.GET, "/users")],
        )
        scenarios = await gen.generate(spec)
        assert len(scenarios) >= 2
        types = {s.scenario_type for s in scenarios}
        assert ChaosScenarioType.LATENCY in types
        assert ChaosScenarioType.ERROR_STATUS in types
        assert ChaosScenarioType.RATE_LIMIT in types

    @pytest.mark.asyncio
    async def test_generate_for_post_endpoint(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        gen = ScenarioGenerator(llm_router=router)
        ep = _make_endpoint(
            HttpMethod.POST,
            request_body=RequestBody(
                fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)]
            ),
        )
        spec = APISpec(title="Test", version="1.0", endpoints=[ep])
        scenarios = await gen.generate(spec)
        tampering = [s for s in scenarios if s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING]
        assert len(tampering) >= 1

    @pytest.mark.asyncio
    async def test_generate_multiple_endpoints(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        gen = ScenarioGenerator(llm_router=router)
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                _make_endpoint(HttpMethod.GET, "/users"),
                _make_endpoint(HttpMethod.POST, "/users"),
            ],
        )
        scenarios = await gen.generate(spec)
        assert len(scenarios) >= 4

    def test_latency_scenario_creation(self):
        gen = ScenarioGenerator.__new__(ScenarioGenerator)
        ep = _make_endpoint(HttpMethod.GET, "/test")
        scenario = gen._latency_scenarios(ep)[0]
        assert scenario.scenario_type == ChaosScenarioType.LATENCY
        assert "delay_ms" in scenario.config

    def test_error_status_scenario_creation(self):
        gen = ScenarioGenerator.__new__(ScenarioGenerator)
        ep = _make_endpoint(HttpMethod.GET, "/test")
        scenario = gen._error_status_scenarios(ep)[0]
        assert scenario.scenario_type == ChaosScenarioType.ERROR_STATUS

    def test_tampering_scenario_creation(self):
        gen = ScenarioGenerator.__new__(ScenarioGenerator)
        ep = _make_endpoint(HttpMethod.POST, "/test")
        field = FieldConstraint(field_name="email", field_type=FieldType.STRING)
        scenarios = gen._field_tampering_scenarios(ep, field)
        assert len(scenarios) > 0
        scenario = scenarios[0]
        assert scenario.scenario_type == ChaosScenarioType.REQUEST_TAMPERING
        assert scenario.config["field_path"] == "email"

    def test_rate_limit_scenario_creation(self):
        gen = ScenarioGenerator.__new__(ScenarioGenerator)
        ep = _make_endpoint(HttpMethod.GET, "/test")
        scenario = gen._rate_limit_scenarios(ep)[0]
        assert scenario.scenario_type == ChaosScenarioType.RATE_LIMIT
        assert "requests_per_second" in scenario.config


# ══════════════════════════════════════════════════════════════
# 1.3 Services — ReportGenerator
# ══════════════════════════════════════════════════════════════


class TestReportGenerator:
    def test_generate_empty_report(self):
        gen = ReportGenerator()
        tr = TestResult(total_scenarios=0)
        report = gen.generate(tr)
        assert report.summary.total_scenarios == 0
        assert report.summary.failed == 0
        assert report.findings == []

    def test_generate_report_with_vulnerabilities(self):
        gen = ReportGenerator()
        tr = TestResult(
            total_scenarios=1,
            results=[
                ScenarioResult(
                    scenario_id="s1",
                    scenario_name="Error Test",
                    scenario_type="error_status",
                    vulnerability_found=True,
                    severity=Severity.HIGH,
                    details="Server returned 500",
                    response=ResponseData(status_code=500),
                )
            ],
        )
        tr.completed_scenarios = 1
        report = gen.generate(tr)
        assert report.summary.failed == 1
        assert len(report.findings) == 1
        assert report.findings[0].severity == Severity.HIGH

    def test_severity_summary(self):
        gen = ReportGenerator()
        tr = TestResult(
            total_scenarios=2,
            results=[
                ScenarioResult(
                    scenario_id="s1",
                    scenario_name="A",
                    scenario_type="error_status",
                    vulnerability_found=True,
                    severity=Severity.HIGH,
                    details="High issue",
                ),
                ScenarioResult(
                    scenario_id="s2",
                    scenario_name="B",
                    scenario_type="latency",
                    vulnerability_found=True,
                    severity=Severity.LOW,
                    details="Low issue",
                ),
            ],
        )
        report = gen.generate(tr)
        assert report.summary.severity_counts.get("high", 0) == 1
        assert report.summary.severity_counts.get("low", 0) == 1

    def test_remediation_suggestions(self):
        gen = ReportGenerator()
        for st, expected_keyword in [
            (ChaosScenarioType.LATENCY, "timeout"),
            (ChaosScenarioType.ERROR_STATUS, "error handling"),
            (ChaosScenarioType.REQUEST_TAMPERING, "validation"),
            (ChaosScenarioType.RATE_LIMIT, "rate limiting"),
        ]:
            result = ScenarioResult(
                scenario_id="s1",
                scenario_name="Test",
                scenario_type=st.value,
                vulnerability_found=True,
                severity=Severity.MEDIUM,
                details="Issue found",
            )
            remediation = gen._suggest_remediation(result)
            assert expected_keyword.lower() in remediation.lower(), f"Missing keyword for {st}"

    def test_reproduction_steps(self):
        gen = ReportGenerator()
        result = ScenarioResult(
            scenario_id="s1",
            scenario_name="Test",
            scenario_type="error_status",
            vulnerability_found=True,
            severity=Severity.MEDIUM,
            response=ResponseData(status_code=500, error="Internal Server Error"),
        )
        remediation = gen._suggest_remediation(result)
        assert isinstance(remediation, str)
        assert len(remediation) > 0

    def test_response_snapshot(self):
        gen = ReportGenerator()
        result = ScenarioResult(
            scenario_id="s1",
            scenario_name="Test",
            scenario_type="error_status",
            vulnerability_found=True,
            severity=Severity.MEDIUM,
            response=ResponseData(
                status_code=500,
                elapsed_ms=123.45,
                error="timeout",
                body={"detail": "error"},
            ),
        )
        finding = gen._extract_findings(TestResult(results=[result], total_scenarios=1))
        if finding:
            assert finding[0].response_status == 500


# ══════════════════════════════════════════════════════════════
# 1.3 Services — LLMRouter
# ══════════════════════════════════════════════════════════════


class TestLLMRouter:
    def test_classify_simple(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        assert router.classify_complexity("change field type of name") == TaskComplexity.SIMPLE
        assert router.classify_complexity("boundary value test") == TaskComplexity.SIMPLE

    def test_classify_complex(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        assert router.classify_complexity("multi-step chained scenario") == TaskComplexity.COMPLEX
        assert (
            router.classify_complexity("analyze business logic exploit") == TaskComplexity.COMPLEX
        )

    def test_classify_medium(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        assert router.classify_complexity("fuzz data for endpoint") == TaskComplexity.MEDIUM

    @pytest.mark.asyncio
    async def test_rule_engine_type_mutation(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        result = await router.route(
            "change field type of 'name' from string to integer",
            complexity=TaskComplexity.SIMPLE,
        )
        data = json.loads(result)
        assert data["mutation"] == "type_change"

    @pytest.mark.asyncio
    async def test_rule_engine_boundary_values(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        result = await router.route(
            "boundary value test for integer field",
            complexity=TaskComplexity.SIMPLE,
        )
        data = json.loads(result)
        assert data["mutation"] == "boundary_values"

    @pytest.mark.asyncio
    async def test_rule_engine_null(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        result = await router.route(
            "replace with null value",
            complexity=TaskComplexity.SIMPLE,
        )
        data = json.loads(result)
        assert data["mutation"] == "null"

    @pytest.mark.asyncio
    async def test_rule_engine_empty_string(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        result = await router.route(
            "replace with empty string",
            complexity=TaskComplexity.SIMPLE,
        )
        data = json.loads(result)
        assert data["mutation"] == "empty_string"

    @pytest.mark.asyncio
    async def test_caching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            router = LLMRouter(
                config={
                    "openai_api_key": "",
                    "anthropic_api_key": "",
                    "cache_dir": tmpdir,
                    "cache_ttl": 60,
                }
            )
            result1 = await router.route(
                "change field type of 'age'",
                complexity=TaskComplexity.SIMPLE,
            )
            result2 = await router.route(
                "change field type of 'age'",
                complexity=TaskComplexity.SIMPLE,
            )
            assert result1 == result2
            router.close()

    @pytest.mark.asyncio
    async def test_batch_route(self):
        router = LLMRouter(config={"openai_api_key": "", "anthropic_api_key": ""})
        prompts = [
            ("change type of name", TaskComplexity.SIMPLE),
            ("boundary test", TaskComplexity.SIMPLE),
        ]
        results = await router.batch_route(prompts)
        assert len(results) == 2
        router.close()


# ══════════════════════════════════════════════════════════════
# 1.3 Services — CircuitBreaker
# ══════════════════════════════════════════════════════════════


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=1.0)
        assert cb.state == "closed"
        assert cb.is_available() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        assert cb.is_available() is False

    def test_success_resets_counter(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == "closed"

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.1)
        assert cb.state == "half-open"

    def test_success_closes_from_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)
        assert cb.state == "half-open"
        cb.record_success()
        assert cb.state == "closed"
