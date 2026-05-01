"""Phase 3: Comprehensive end-to-end tests.

5 full rounds of the complete system workflow, covering all core functions
and boundary scenarios. Each round must pass with zero errors and warnings.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.main import app
from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    Finding,
    Report,
    ResponseData,
    ScenarioResult,
    Severity,
    TestResult,
)
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType
from api_chaos_agent.models.schema import (
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    Parameter,
    RequestBody,
)
from api_chaos_agent.routers.execution import set_mock_transport
from api_chaos_agent.services.execution_engine import ExecutionEngine
from api_chaos_agent.services.report_generator import ReportGenerator
from api_chaos_agent.services.scenario_generator import ScenarioGenerator
from api_chaos_agent.services.schema_parser import SchemaParser
from api_chaos_agent.services.store import store

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PETSTORE_JSON = FIXTURES_DIR / "petstore_openapi.json"
PETSTORE_YAML = FIXTURES_DIR / "petstore_openapi.yaml"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(200, json={"data": "ok", "items": []})
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


@pytest.fixture(autouse=True)
def clean_state():
    store.clear_sync()
    set_mock_transport(MOCK_TRANSPORT)
    yield
    store.clear_sync()
    set_mock_transport(None)


@pytest.fixture
def client():
    return TestClient(app)


def _upload_json(client, path=PETSTORE_JSON, filename="petstore.json"):
    data = path.read_bytes()
    return client.post(
        "/api/schemas/upload",
        files={"file": (filename, data, "application/json")},
    )


def _upload_yaml(client, path=PETSTORE_YAML, filename="petstore.yaml"):
    data = path.read_bytes()
    return client.post(
        "/api/schemas/upload",
        files={"file": (filename, data, "application/x-yaml")},
    )


# ======================================================================
# Round 1: Standard happy-path workflow
# ======================================================================


class TestRound1StandardWorkflow:
    def test_r1_full_json_workflow(self, client):
        upload_resp = _upload_json(client)
        assert upload_resp.status_code in (200, 201)
        schema_id = upload_resp.json()["schema_id"]
        assert "schema_id" in upload_resp.json()
        assert upload_resp.json()["title"] == "Petstore API"
        assert upload_resp.json()["endpoints"] >= 2

        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["scenarios_generated"] > 0
        scenario_ids = gen_data["scenario_ids"]

        exec_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids,
                "base_url": "https://petstore.example.com/v1",
                "timeout_seconds": 5.0,
                "serial": True,
            },
        )
        assert exec_resp.status_code == 200
        execution_id = exec_resp.json()["execution_id"]

        exec_detail = client.get(f"/api/executions/{execution_id}")
        assert exec_detail.status_code == 200
        assert exec_detail.json()["total_scenarios"] == len(scenario_ids)

        report_resp = client.post(f"/api/reports/generate/{execution_id}")
        assert report_resp.status_code == 200
        report_id = report_resp.json()["report_id"]

        get_report = client.get(f"/api/reports/{report_id}")
        assert get_report.status_code == 200
        report = get_report.json()
        assert "findings" in report
        assert "summary" in report

    def test_r1_full_yaml_workflow(self, client):
        upload_resp = _upload_yaml(client)
        assert upload_resp.status_code in (200, 201)
        upload_resp.json()["schema_id"]
        assert upload_resp.json()["endpoints"] >= 1

    def test_r1_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_r1_readiness_check(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_r1_liveness_check(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"


# ======================================================================
# Round 2: Boundary and edge case scenarios
# ======================================================================


class TestRound2BoundaryScenarios:
    def test_r2_empty_scenario_list_rejected(self, client):
        resp = client.post(
            "/api/executions/",
            params={"scenario_ids": [], "base_url": "https://example.com"},
        )
        assert resp.status_code in (400, 422)

    def test_r2_nonexistent_schema_returns_404(self, client):
        resp = client.get("/api/schemas/nonexistent-id")
        assert resp.status_code == 404

    def test_r2_nonexistent_scenario_returns_404(self, client):
        resp = client.get("/api/scenarios/nonexistent-id")
        assert resp.status_code == 404

    def test_r2_nonexistent_execution_returns_404(self, client):
        resp = client.get("/api/executions/nonexistent-id")
        assert resp.status_code == 404

    def test_r2_nonexistent_report_returns_404(self, client):
        resp = client.get("/api/reports/nonexistent-id")
        assert resp.status_code == 404

    def test_r2_invalid_file_upload_rejected(self, client):
        resp = client.post(
            "/api/schemas/upload",
            files={"file": ("bad.txt", b"not a spec", "text/plain")},
        )
        assert resp.status_code == 400

    def test_r2_report_for_nonexistent_execution(self, client):
        resp = client.post("/api/reports/generate/nonexistent")
        assert resp.status_code == 404

    def test_r2_execution_with_nonexistent_scenario(self, client):
        resp = client.post(
            "/api/executions/",
            params={"scenario_ids": ["nonexistent"], "base_url": "https://example.com"},
        )
        assert resp.status_code == 404

    def test_r2_empty_file_rejected(self, client):
        resp = client.post(
            "/api/schemas/upload",
            files={"file": ("empty.json", b"", "application/json")},
        )
        assert resp.status_code == 400


# ======================================================================
# Round 3: Service-layer deep validation
# ======================================================================


class TestRound3ServiceLayerValidation:
    def test_r3_schema_parser_json(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))
        assert spec.title == "Petstore API"
        assert len(spec.endpoints) >= 2
        assert spec.base_url is not None

    def test_r3_schema_parser_yaml(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_YAML))
        assert "Petstore" in spec.title or len(spec.endpoints) >= 1
        assert len(spec.endpoints) >= 1

    @pytest.mark.asyncio
    async def test_r3_scenario_generator_all_types(self):
        generator = ScenarioGenerator()
        endpoint = Endpoint(path="/test", method=HttpMethod.GET)
        scenarios = await generator._generate_for_endpoint(endpoint)
        types = {s.scenario_type for s in scenarios}
        assert ChaosScenarioType.LATENCY in types
        assert ChaosScenarioType.ERROR_STATUS in types
        assert ChaosScenarioType.RATE_LIMIT in types

    @pytest.mark.asyncio
    async def test_r3_scenario_generator_with_body(self):
        generator = ScenarioGenerator()
        body = RequestBody(
            content_type="application/json",
            required=True,
            fields=[
                FieldConstraint(
                    field_name="email", field_type=FieldType.STRING, required=True, format="email"
                ),
                FieldConstraint(
                    field_name="age",
                    field_type=FieldType.INTEGER,
                    required=False,
                    minimum=0,
                    maximum=150,
                ),
            ],
        )
        endpoint = Endpoint(path="/users", method=HttpMethod.POST, request_body=body)
        scenarios = await generator._generate_for_endpoint(endpoint)
        types = {s.scenario_type for s in scenarios}
        assert ChaosScenarioType.REQUEST_TAMPERING in types

    @pytest.mark.asyncio
    async def test_r3_execution_engine_serial(self):
        scenario = ChaosScenario(
            id="test-1",
            name="Test",
            scenario_type=ChaosScenarioType.LATENCY,
            endpoint=Endpoint(path="/test", method=HttpMethod.GET),
            config={"delay_ms": 100},
            severity=Severity.MEDIUM,
        )
        config = ExecutionConfig(
            base_url="https://api.example.com", serial=True, timeout_seconds=5.0
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_r3_execution_engine_parallel(self):
        scenarios = [
            ChaosScenario(
                id=f"test-{i}",
                name=f"Test {i}",
                scenario_type=ChaosScenarioType.ERROR_STATUS,
                endpoint=Endpoint(path="/test", method=HttpMethod.GET),
                config={"status_code": 500, "repeat_count": 1},
                severity=Severity.HIGH,
            )
            for i in range(5)
        ]
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=3, timeout_seconds=5.0
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 5

    def test_r3_report_generator_returns_report(self):
        test_result = TestResult(total_scenarios=1, completed_scenarios=1)
        test_result.results.append(
            ScenarioResult(
                scenario_id="s1",
                scenario_name="Test",
                scenario_type="latency",
                status=ExecutionStatus.COMPLETED,
                severity=Severity.MEDIUM,
                response=ResponseData(status_code=200, elapsed_ms=100.0),
                vulnerability_found=True,
                details="Slow response detected",
            )
        )
        generator = ReportGenerator()
        report = generator.generate(test_result)
        assert isinstance(report, Report)
        assert len(report.findings) > 0
        assert report.summary.total_scenarios == 1

    def test_r3_report_generator_findings_have_remediation(self):
        test_result = TestResult(total_scenarios=2, completed_scenarios=1, failed_scenarios=1)
        test_result.results.append(
            ScenarioResult(
                scenario_id="s1",
                scenario_name="Latency Test",
                scenario_type="latency",
                status=ExecutionStatus.COMPLETED,
                severity=Severity.HIGH,
                response=ResponseData(status_code=200, elapsed_ms=5000.0),
            )
        )
        test_result.results.append(
            ScenarioResult(
                scenario_id="s2",
                scenario_name="Error Test",
                scenario_type="error_status",
                status=ExecutionStatus.FAILED,
                severity=Severity.CRITICAL,
                response=ResponseData(status_code=500, elapsed_ms=100.0),
            )
        )
        generator = ReportGenerator()
        report = generator.generate(test_result)
        for finding in report.findings:
            assert finding.recommendation is not None
            assert len(finding.recommendation) > 0


# ======================================================================
# Round 4: Data model integrity and cross-module consistency
# ======================================================================


class TestRound4DataModelIntegrity:
    def test_r4_endpoint_model_fields(self):
        ep = Endpoint(
            path="/users",
            method=HttpMethod.POST,
            summary="Create user",
            parameters=[
                Parameter(name="id", location="path", param_type=FieldType.STRING, required=True)
            ],
            request_body=RequestBody(content_type="application/json", required=True),
            tags=["users"],
            operation_id="createUser",
        )
        assert ep.path == "/users"
        assert ep.method == HttpMethod.POST
        assert len(ep.parameters) == 1
        assert ep.request_body is not None

    def test_r4_chaos_scenario_model_fields(self):
        scenario = ChaosScenario(
            id="sc-1",
            name="Latency Test",
            scenario_type=ChaosScenarioType.LATENCY,
            endpoint=Endpoint(path="/test", method=HttpMethod.GET),
            config={"delay_ms": 500},
            severity=Severity.HIGH,
        )
        assert scenario.scenario_type == ChaosScenarioType.LATENCY
        assert scenario.severity == Severity.HIGH

    def test_r4_execution_config_fields(self):
        config = ExecutionConfig(
            base_url="https://api.example.com",
            concurrency=10,
            timeout_seconds=30.0,
            max_retries=2,
        )
        assert config.concurrency == 10
        assert config.timeout_seconds == 30.0

    def test_r4_severity_enum_values(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"

    def test_r4_chaos_scenario_type_enum(self):
        assert ChaosScenarioType.LATENCY.value == "latency"
        assert ChaosScenarioType.ERROR_STATUS.value == "error_status"
        assert ChaosScenarioType.REQUEST_TAMPERING.value == "request_tampering"
        assert ChaosScenarioType.RATE_LIMIT.value == "rate_limit"

    def test_r4_http_method_enum(self):
        assert HttpMethod.GET.value == "GET"
        assert HttpMethod.POST.value == "POST"
        assert HttpMethod.PUT.value == "PUT"
        assert HttpMethod.DELETE.value == "DELETE"

    def test_r4_field_type_enum(self):
        assert FieldType.STRING.value == "string"
        assert FieldType.INTEGER.value == "integer"
        assert FieldType.BOOLEAN.value == "boolean"
        assert FieldType.ARRAY.value == "array"

    def test_r4_response_data_model(self):
        resp = ResponseData(status_code=200, elapsed_ms=50.0, body={"ok": True})
        assert resp.status_code == 200
        assert resp.elapsed_ms == 50.0
        assert resp.error is None

    def test_r4_finding_model(self):
        finding = Finding(
            scenario_id="s1",
            scenario_name="Test",
            scenario_type="latency",
            endpoint_path="/test",
            endpoint_method="GET",
            severity=Severity.HIGH,
            vulnerability_found=True,
            details="Server crashed on tampered input",
            recommendation="Add input validation",
        )
        assert finding.vulnerability_found is True
        assert finding.recommendation == "Add input validation"


# ======================================================================
# Round 5: Stress and concurrency scenarios
# ======================================================================


class TestRound5StressConcurrency:
    def test_r5_multiple_schema_uploads(self, client):
        for i in range(3):
            resp = _upload_json(client, filename=f"petstore_{i}.json")
            assert resp.status_code in (200, 201)

    def test_r5_multiple_scenario_generations(self, client):
        upload_resp = _upload_json(client)
        schema_id = upload_resp.json()["schema_id"]

        for _ in range(3):
            gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
            assert gen_resp.status_code == 200
            assert gen_resp.json()["scenarios_generated"] > 0

    @pytest.mark.asyncio
    async def test_r5_parallel_execution_many_scenarios(self):
        scenarios = [
            ChaosScenario(
                id=f"stress-{i}",
                name=f"Stress {i}",
                scenario_type=ChaosScenarioType.ERROR_STATUS,
                endpoint=Endpoint(path="/test", method=HttpMethod.GET),
                config={"status_code": 500, "repeat_count": 1},
                severity=Severity.MEDIUM,
            )
            for i in range(20)
        ]
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=10, timeout_seconds=5.0
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute(scenarios)
        assert result.total_scenarios == 20
        assert result.completed_scenarios + result.failed_scenarios == 20

    @pytest.mark.asyncio
    async def test_r5_mixed_scenario_types_execution(self):
        endpoint = Endpoint(path="/test", method=HttpMethod.GET)
        generator = ScenarioGenerator()
        all_scenarios = await generator._generate_for_endpoint(endpoint)
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=5, timeout_seconds=5.0, serial=True
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute(all_scenarios)
        assert result.total_scenarios == len(all_scenarios)
        types = {r.scenario_type for r in result.results}
        assert len(types) >= 2

    def test_r5_report_generation_after_stress(self):
        test_result = TestResult(total_scenarios=20, completed_scenarios=18, failed_scenarios=2)
        for i in range(20):
            is_vuln = i < 10
            test_result.results.append(
                ScenarioResult(
                    scenario_id=f"s-{i}",
                    scenario_name=f"Scenario {i}",
                    scenario_type="latency" if i % 2 == 0 else "error_status",
                    status=ExecutionStatus.COMPLETED if i < 18 else ExecutionStatus.FAILED,
                    severity=Severity.MEDIUM,
                    response=ResponseData(status_code=200 if i < 18 else None, elapsed_ms=100.0),
                    vulnerability_found=is_vuln,
                    details=f"Vulnerability in scenario {i}" if is_vuln else "",
                )
            )
        generator = ReportGenerator()
        report = generator.generate(test_result)
        assert report.summary.total_scenarios == 20
        assert len(report.findings) == 10

    def test_r5_full_workflow_with_minimal_scenarios(self, client):
        upload_resp = _upload_json(client)
        schema_id = upload_resp.json()["schema_id"]

        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code == 200
        scenario_ids = gen_resp.json()["scenario_ids"][:1]

        exec_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids,
                "base_url": "https://petstore.example.com/v1",
                "timeout_seconds": 5.0,
                "serial": True,
            },
        )
        assert exec_resp.status_code == 200

        execution_id = exec_resp.json()["execution_id"]
        report_resp = client.post(f"/api/reports/generate/{execution_id}")
        assert report_resp.status_code == 200
