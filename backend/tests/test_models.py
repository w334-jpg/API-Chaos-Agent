"""Phase 1: Node-level test for data model layer validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    Finding,
    Report,
    ReportSummary,
    ResponseData,
    ScenarioResult,
    TestResult,
)
from api_chaos_agent.models.scenario import (
    ChaosScenario,
    ChaosScenarioType,
    ErrorStatusConfig,
    LatencyConfig,
    RateLimitConfig,
    Severity,
    TamperingConfig,
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


class TestSchemaModels:
    def test_http_method_enum(self):
        for m in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
            assert HttpMethod(m).value == m

    def test_field_type_enum(self):
        for t in ["string", "integer", "number", "boolean", "array", "object", "null"]:
            assert FieldType(t).value == t

    def test_field_constraint_defaults(self):
        fc = FieldConstraint(field_name="test", field_type=FieldType.STRING)
        assert fc.required is False
        assert fc.min_length is None
        assert fc.max_length is None
        assert fc.pattern is None
        assert fc.enum_values is None

    def test_field_constraint_with_all_fields(self):
        fc = FieldConstraint(
            field_name="email",
            field_type=FieldType.STRING,
            required=True,
            min_length=5,
            max_length=100,
            pattern=r"^[^@]+@[^@]+$",
            format="email",
            enum_values=None,
            default="user@example.com",
        )
        assert fc.required is True
        assert fc.format == "email"

    def test_parameter_model(self):
        p = Parameter(name="id", location="path", param_type=FieldType.STRING, required=True)
        assert p.location == "path"
        assert p.param_type == FieldType.STRING

    def test_request_body_model(self):
        rb = RequestBody(content_type="application/json", required=True)
        assert rb.fields == []
        assert rb.raw_schema == {}

    def test_response_spec_model(self):
        rs = ResponseSpec(
            status_code="200", description="OK", content_type="application/json", schema_ref="Pet"
        )
        assert rs.status_code == "200"
        assert rs.schema_ref == "Pet"

    def test_endpoint_model(self):
        ep = Endpoint(path="/users", method=HttpMethod.GET, summary="List users")
        assert ep.parameters == []
        assert ep.request_body is None
        assert ep.responses == []
        assert ep.tags == []

    def test_api_spec_model(self):
        spec = APISpec(title="Test API", version="1.0.0")
        assert spec.endpoints == []
        assert spec.base_url is None
        assert spec.raw_spec == {}

    def test_api_spec_with_endpoints(self):
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(path="/a", method=HttpMethod.GET),
                Endpoint(path="/b", method=HttpMethod.POST),
            ],
        )
        assert len(spec.endpoints) == 2


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

    def test_latency_config(self):
        lc = LatencyConfig(delay_ms=500, jitter_ms=100)
        assert lc.delay_ms == 500
        assert lc.jitter_ms == 100

    def test_latency_config_rejects_negative(self):
        with pytest.raises(ValidationError):
            LatencyConfig(delay_ms=-1)

    def test_error_status_config(self):
        ec = ErrorStatusConfig(status_code=500, repeat_count=3)
        assert ec.status_code == 500
        assert ec.repeat_count == 3

    def test_error_status_config_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            ErrorStatusConfig(status_code=999)

    def test_tampering_config(self):
        tc = TamperingConfig(
            field_path="name", tamper_type="inject", tamper_value="'; DROP TABLE --"
        )
        assert tc.tamper_type == "inject"

    def test_rate_limit_config(self):
        rc = RateLimitConfig(requests_per_second=100, duration_seconds=30)
        assert rc.requests_per_second == 100
        assert rc.duration_seconds == 30

    def test_rate_limit_config_rejects_zero_rps(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(requests_per_second=0)

    def test_chaos_scenario_model(self):
        scenario = ChaosScenario(
            id="sc-1",
            name="Test",
            scenario_type=ChaosScenarioType.LATENCY,
            endpoint=Endpoint(path="/test", method=HttpMethod.GET),
            config={"delay_ms": 100},
            severity=Severity.MEDIUM,
        )
        assert scenario.id == "sc-1"
        assert scenario.description == ""

    def test_chaos_scenario_default_id(self):
        scenario = ChaosScenario(
            name="Test",
            scenario_type=ChaosScenarioType.LATENCY,
            endpoint=Endpoint(path="/test", method=HttpMethod.GET),
            config={"delay_ms": 100},
        )
        assert scenario.id == ""


class TestReportModels:
    def test_execution_status_enum(self):
        for s in ["pending", "running", "completed", "failed", "timeout"]:
            assert ExecutionStatus(s).value == s

    def test_execution_config_defaults(self):
        config = ExecutionConfig(base_url="https://api.example.com")
        assert config.concurrency == 10
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 2
        assert config.serial is False

    def test_execution_config_custom(self):
        config = ExecutionConfig(
            base_url="https://api.example.com",
            concurrency=50,
            timeout_seconds=60.0,
            max_retries=5,
            retry_delay_seconds=2.0,
            headers={"Authorization": "Bearer token"},
            proxy="http://proxy:8080",
            serial=True,
        )
        assert config.concurrency == 50
        assert config.headers["Authorization"] == "Bearer token"
        assert config.proxy == "http://proxy:8080"

    def test_execution_config_rejects_invalid_concurrency(self):
        with pytest.raises(ValidationError):
            ExecutionConfig(base_url="https://api.example.com", concurrency=0)
        with pytest.raises(ValidationError):
            ExecutionConfig(base_url="https://api.example.com", concurrency=1001)

    def test_execution_config_rejects_invalid_timeout(self):
        with pytest.raises(ValidationError):
            ExecutionConfig(base_url="https://api.example.com", timeout_seconds=0.5)

    def test_response_data_defaults(self):
        rd = ResponseData()
        assert rd.status_code is None
        assert rd.headers == {}
        assert rd.body is None
        assert rd.elapsed_ms == 0.0
        assert rd.error is None

    def test_scenario_result_model(self):
        sr = ScenarioResult(scenario_id="s1", scenario_name="Test", scenario_type="latency")
        assert sr.status == ExecutionStatus.PENDING
        assert sr.vulnerability_found is False

    def test_test_result_model(self):
        tr = TestResult(total_scenarios=5, completed_scenarios=3, failed_scenarios=1)
        assert tr.results == []
        assert tr.config is None

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
        assert f.recommendation == ""

    def test_report_model(self):
        r = Report(id="test", schema_id="test", summary=ReportSummary())
        assert r.summary.total_scenarios == 0
        assert r.summary.failed == 0
        assert r.summary.severity_counts == {}
        assert r.findings == []

    def test_report_with_findings(self):
        r = Report(
            id="full-report",
            schema_id="test",
            summary=ReportSummary(total_scenarios=10, failed=1, severity_counts={"high": 1}),
            findings=[
                Finding(
                    scenario_id="s1",
                    scenario_name="F1",
                    scenario_type="latency",
                    endpoint_path="/a",
                    endpoint_method="GET",
                    severity=Severity.HIGH,
                    vulnerability_found=True,
                    details="D1",
                ),
            ],
        )
        assert len(r.findings) == 1
        assert r.summary.severity_counts["high"] == 1

    def test_models_serialize_to_dict(self):
        ep = Endpoint(path="/test", method=HttpMethod.GET)
        d = ep.model_dump()
        assert d["path"] == "/test"
        assert d["method"] == "GET"

    def test_models_serialize_to_json(self):
        scenario = ChaosScenario(
            id="sc-1",
            name="Test",
            scenario_type=ChaosScenarioType.LATENCY,
            endpoint=Endpoint(path="/test", method=HttpMethod.GET),
            config={"delay_ms": 100},
            severity=Severity.MEDIUM,
        )
        json_str = scenario.model_dump_json()
        data = __import__("json").loads(json_str)
        assert data["id"] == "sc-1"
        assert data["scenario_type"] == "latency"
