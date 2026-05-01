"""Phase 2: Block-level integration tests.

Tests related modules working together as functional blocks.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from api_chaos_agent.models.report import ExecutionConfig, Severity
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType
from api_chaos_agent.models.schema import (
    APISpec,
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    RequestBody,
)
from api_chaos_agent.services.execution_engine import ExecutionEngine
from api_chaos_agent.services.llm_router import LLMRouter
from api_chaos_agent.services.report_generator import ReportGenerator
from api_chaos_agent.services.scenario_generator import ScenarioGenerator
from api_chaos_agent.services.schema_parser import SchemaParser

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PETSTORE_JSON = FIXTURES_DIR / "petstore_openapi.json"
PETSTORE_YAML = FIXTURES_DIR / "petstore_openapi.yaml"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(200, json={"data": "ok"})
    if request.method == "POST":
        return httpx.Response(201, json={"id": 1, "created": True})
    if request.method == "DELETE":
        return httpx.Response(204)
    if request.method == "PUT":
        return httpx.Response(200, json={"updated": True})
    return httpx.Response(200, json={"status": "ok"})


MOCK_TRANSPORT = httpx.MockTransport(_mock_handler)


class TestSchemaParserScenarioGeneratorBlock:
    @pytest.mark.asyncio
    async def test_parse_json_then_generate_scenarios(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))
        assert len(spec.endpoints) > 0

        generator = ScenarioGenerator()
        scenarios = await generator.generate(spec)
        assert len(scenarios) > 0
        for s in scenarios:
            assert s.endpoint.path in {e.path for e in spec.endpoints}

    @pytest.mark.asyncio
    async def test_parse_yaml_then_generate_all_types(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_YAML))
        assert len(spec.endpoints) > 0

        generator = ScenarioGenerator()
        scenarios = await generator.generate(spec)
        types = {s.scenario_type for s in scenarios}
        assert ChaosScenarioType.LATENCY in types
        assert ChaosScenarioType.ERROR_STATUS in types
        assert ChaosScenarioType.RATE_LIMIT in types

    @pytest.mark.asyncio
    async def test_parse_then_generate_tampering_for_post_endpoints(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))

        generator = ScenarioGenerator()
        scenarios = await generator.generate(spec)
        tampering = [s for s in scenarios if s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING]
        post_endpoints = [e for e in spec.endpoints if e.method == HttpMethod.POST]
        if post_endpoints:
            assert len(tampering) > 0

    @pytest.mark.asyncio
    async def test_parse_then_batch_generate_for_spec(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))

        generator = ScenarioGenerator()
        all_scenarios = await generator.generate(spec)
        assert len(all_scenarios) >= len(spec.endpoints) * 3

    @pytest.mark.asyncio
    async def test_parse_then_generate_with_type_filter(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))

        generator = ScenarioGenerator()
        all_scenarios = await generator.generate(spec)
        latency = [s for s in all_scenarios if s.scenario_type == ChaosScenarioType.LATENCY]
        assert len(latency) > 0
        assert all(s.scenario_type == ChaosScenarioType.LATENCY for s in latency)

    @pytest.mark.asyncio
    async def test_field_constraints_flow_from_parser_to_tampering(self):
        parser = SchemaParser()
        spec = parser.parse(str(PETSTORE_JSON))

        generator = ScenarioGenerator()
        scenarios = await generator.generate(spec)
        tampering = [s for s in scenarios if s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING]
        for t in tampering:
            assert "field_path" in t.config


class TestScenarioGeneratorExecutionEngineBlock:
    def _make_endpoint(self, method=HttpMethod.GET, path="/test", body=None):
        return Endpoint(path=path, method=method, summary="Test endpoint", request_body=body)

    @pytest.mark.asyncio
    async def test_generate_latency_then_execute(self):
        generator = ScenarioGenerator()
        endpoint = self._make_endpoint()
        scenario = generator._latency_scenarios(endpoint)[0]
        assert scenario is not None

        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_generate_error_then_execute(self):
        generator = ScenarioGenerator()
        endpoint = self._make_endpoint()
        scenario = generator._error_status_scenarios(endpoint)[0]
        assert scenario is not None

        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_generate_tampering_then_execute(self):
        generator = ScenarioGenerator()
        body = RequestBody(
            content_type="application/json",
            required=True,
            fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING, required=True)],
        )
        endpoint = self._make_endpoint(method=HttpMethod.POST, body=body)
        scenario = generator._tampering_scenarios(endpoint)[0]
        assert scenario is not None

        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_generate_rate_limit_then_execute(self):
        generator = ScenarioGenerator()
        endpoint = self._make_endpoint()
        scenario = generator._rate_limit_scenarios(endpoint)[0]
        assert scenario is not None

        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute([scenario])
        assert result.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_generate_all_types_then_execute_mixed(self):
        generator = ScenarioGenerator()
        endpoint = self._make_endpoint()
        all_scenarios = [
            generator._latency_scenarios(endpoint)[0],
            generator._error_status_scenarios(endpoint)[0],
            generator._rate_limit_scenarios(endpoint)[0],
        ]

        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute(all_scenarios)
        assert result.total_scenarios == 3
        types = {r.scenario_type for r in result.results}
        assert len(types) > 1


class TestExecutionEngineReportGeneratorBlock:
    def _make_scenario(self, stype=ChaosScenarioType.LATENCY):
        return ChaosScenario(
            id="test-scenario-1",
            name=f"Test {stype.value}",
            scenario_type=stype,
            endpoint=Endpoint(path="/api/test", method=HttpMethod.GET),
            config={"delay_ms": 100},
            severity=Severity.MEDIUM,
        )

    @pytest.mark.asyncio
    async def test_execute_then_generate_report(self):
        scenario = self._make_scenario()
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute([scenario])

        generator = ReportGenerator()
        report = generator.generate(result)
        assert report is not None
        assert report.summary.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_execute_multiple_then_report_has_all_findings(self):
        scenarios = [
            ChaosScenario(
                id=f"sc-{i}",
                name=f"Scenario {i}",
                scenario_type=ChaosScenarioType.LATENCY,
                endpoint=Endpoint(path=f"/api/test{i}", method=HttpMethod.GET),
                config={"delay_ms": 100},
                severity=Severity.MEDIUM,
            )
            for i in range(5)
        ]
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=MOCK_TRANSPORT)
        result = await engine.execute(scenarios)

        generator = ReportGenerator()
        report = generator.generate(result)
        assert report.summary.total_scenarios == 5

    @pytest.mark.asyncio
    async def test_execute_tampering_then_report_classifies_vulnerability(self):
        def _tamper_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": 1, "name": "' OR 1=1 --"})

        tamper_transport = httpx.MockTransport(_tamper_handler)

        scenario = ChaosScenario(
            id="tamper-1",
            name="SQL Injection Test",
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            endpoint=Endpoint(path="/api/users", method=HttpMethod.POST),
            config={"field_path": "name", "tamper_type": "inject", "tamper_value": "' OR 1=1 --"},
            severity=Severity.HIGH,
        )
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=tamper_transport)
        result = await engine.execute([scenario])

        generator = ReportGenerator()
        report = generator.generate(result)
        assert report.summary.failed > 0

    @pytest.mark.asyncio
    async def test_execute_rate_limit_no_protection_then_report_flags(self):
        def _no_rate_limit_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

        rate_transport = httpx.MockTransport(_no_rate_limit_handler)

        scenario = ChaosScenario(
            id="rate-1",
            name="Rate Limit Test",
            scenario_type=ChaosScenarioType.RATE_LIMIT,
            endpoint=Endpoint(path="/api/data", method=HttpMethod.GET),
            config={"requests_per_second": 10, "duration_seconds": 1},
            severity=Severity.MEDIUM,
        )
        config = ExecutionConfig(
            base_url="https://api.example.com", concurrency=1, timeout_seconds=5
        )
        engine = ExecutionEngine(config, transport=rate_transport)
        result = await engine.execute([scenario])

        generator = ReportGenerator()
        report = generator.generate(result)
        assert report.summary.failed >= 1


class TestLLMRouterScenarioGeneratorBlock:
    def test_rule_engine_generates_without_llm(self):
        generator = ScenarioGenerator(llm_router=None)
        endpoint = Endpoint(path="/api/test", method=HttpMethod.GET)
        scenario = generator._latency_scenarios(endpoint)[0]
        assert scenario is not None
        assert scenario.scenario_type == ChaosScenarioType.LATENCY

    @pytest.mark.asyncio
    async def test_llm_enhancement_adds_scenarios(self):
        mock_router = MagicMock(spec=LLMRouter)
        mock_router.route = AsyncMock(
            return_value=json.dumps(
                [
                    {
                        "name": "AI-Generated Edge Case",
                        "type": "latency",
                        "config": {"delay_ms": 9999},
                        "severity": "high",
                    }
                ]
            )
        )

        generator = ScenarioGenerator(llm_router=mock_router)
        spec = APISpec(
            title="Test",
            version="1.0.0",
            endpoints=[Endpoint(path="/api/test", method=HttpMethod.GET)],
        )
        await generator.generate(spec)
        mock_router.route.assert_awaited()

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_base_scenarios(self):
        mock_router = MagicMock(spec=LLMRouter)
        mock_router.route = AsyncMock(side_effect=Exception("LLM unavailable"))

        generator = ScenarioGenerator(llm_router=mock_router)
        spec = APISpec(
            title="Test",
            version="1.0.0",
            endpoints=[Endpoint(path="/api/test", method=HttpMethod.GET)],
        )
        scenarios = await generator.generate(spec)
        assert len(scenarios) > 0


class TestFullAPIRouteBlock:
    def test_full_api_chain(self):
        from fastapi.testclient import TestClient

        from api_chaos_agent.main import app
        from api_chaos_agent.routers.execution import set_mock_transport
        from api_chaos_agent.services.store import store

        store.clear_sync()
        set_mock_transport(MOCK_TRANSPORT)

        try:
            client = TestClient(app)
            petstore_bytes = PETSTORE_JSON.read_bytes()

            upload_resp = client.post(
                "/api/schemas/upload",
                files={"file": ("petstore.json", petstore_bytes, "application/json")},
            )
            assert upload_resp.status_code in (200, 201)
            schema_id = upload_resp.json()["schema_id"]

            gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
            assert gen_resp.status_code in (200, 201)
        finally:
            store.clear_sync()
            set_mock_transport(None)

    def test_api_error_handling_chain(self):
        from fastapi.testclient import TestClient

        from api_chaos_agent.main import app
        from api_chaos_agent.services.store import store

        store.clear_sync()
        try:
            client = TestClient(app)

            bad_upload = client.post(
                "/api/schemas/upload",
                files={"file": ("bad.txt", b"invalid", "text/plain")},
            )
            assert bad_upload.status_code in (400, 422)

            missing_schema = client.get("/api/schemas/nonexistent")
            assert missing_schema.status_code == 404

            missing_scenario = client.get("/api/scenarios/nonexistent")
            assert missing_scenario.status_code == 404

            missing_report = client.get("/api/reports/nonexistent")
            assert missing_report.status_code == 404
        finally:
            store.clear_sync()
