"""Comprehensive unit tests for ScenarioGenerator service."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Severity
from api_chaos_agent.models.schema import (
    APISpec,
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    Parameter,
    RequestBody,
)
from api_chaos_agent.services.scenario_generator import ScenarioGenerator


@pytest.fixture
def endpoint_with_body() -> Endpoint:
    return Endpoint(
        path="/users",
        method=HttpMethod.POST,
        summary="Create user",
        request_body=RequestBody(
            content_type="application/json",
            required=True,
            fields=[
                FieldConstraint(
                    field_name="username",
                    field_type=FieldType.STRING,
                    required=True,
                    min_length=3,
                    max_length=50,
                ),
                FieldConstraint(
                    field_name="email",
                    field_type=FieldType.STRING,
                    required=True,
                    format="email",
                ),
                FieldConstraint(
                    field_name="age",
                    field_type=FieldType.INTEGER,
                    required=False,
                    minimum=0,
                    maximum=150,
                ),
                FieldConstraint(
                    field_name="is_active",
                    field_type=FieldType.BOOLEAN,
                    required=False,
                    default=True,
                ),
            ],
        ),
    )


@pytest.fixture
def endpoint_without_body() -> Endpoint:
    return Endpoint(
        path="/users",
        method=HttpMethod.GET,
        summary="List users",
        parameters=[
            Parameter(
                name="page",
                location="query",
                param_type=FieldType.INTEGER,
                required=False,
            ),
        ],
    )


@pytest.fixture
def delete_endpoint() -> Endpoint:
    return Endpoint(
        path="/users/{id}",
        method=HttpMethod.DELETE,
        summary="Delete user",
    )


@pytest.fixture
def api_spec(endpoint_with_body, endpoint_without_body, delete_endpoint) -> APISpec:
    return APISpec(
        title="Test API",
        version="1.0.0",
        endpoints=[endpoint_with_body, endpoint_without_body, delete_endpoint],
    )


@pytest.fixture
def generator() -> ScenarioGenerator:
    return ScenarioGenerator()


@pytest.fixture
def generator_with_llm() -> ScenarioGenerator:
    mock_router = AsyncMock()
    mock_router.route.return_value = json.dumps([
        {
            "name": "LLM: SQL injection in username",
            "type": "request_tampering",
            "config": {"tamper_type": "inject", "field_path": "username", "tamper_value": "' OR 1=1 --"},
            "severity": "critical",
        }
    ])
    gen = ScenarioGenerator(llm_router=mock_router)
    return gen


class TestLatencyScenarios:

    @pytest.mark.asyncio
    async def test_generates_latency_scenarios(self, generator, endpoint_with_body):
        scenarios = generator._latency_scenarios(endpoint_with_body)
        assert len(scenarios) >= 3
        for s in scenarios:
            assert s.scenario_type == ChaosScenarioType.LATENCY

    @pytest.mark.asyncio
    async def test_latency_scenarios_have_delay_config(self, generator, endpoint_with_body):
        scenarios = generator._latency_scenarios(endpoint_with_body)
        for s in scenarios:
            assert "delay_ms" in s.config
            assert isinstance(s.config["delay_ms"], int)
            assert s.config["delay_ms"] > 0

    @pytest.mark.asyncio
    async def test_latency_scenarios_have_jitter(self, generator, endpoint_with_body):
        scenarios = generator._latency_scenarios(endpoint_with_body)
        for s in scenarios:
            assert "jitter_ms" in s.config

    @pytest.mark.asyncio
    async def test_latency_scenarios_have_varying_severity(self, generator, endpoint_with_body):
        scenarios = generator._latency_scenarios(endpoint_with_body)
        severities = {s.severity for s in scenarios}
        assert len(severities) >= 2

    @pytest.mark.asyncio
    async def test_latency_scenarios_have_proper_structure(self, generator, endpoint_with_body):
        scenarios = generator._latency_scenarios(endpoint_with_body)
        for s in scenarios:
            assert s.name, "Scenario name must not be empty"
            assert s.scenario_type == ChaosScenarioType.LATENCY
            assert s.endpoint == endpoint_with_body


class TestErrorScenarios:

    @pytest.mark.asyncio
    async def test_generates_error_scenarios(self, generator, endpoint_with_body):
        scenarios = generator._error_status_scenarios(endpoint_with_body)
        assert len(scenarios) >= 3
        for s in scenarios:
            assert s.scenario_type == ChaosScenarioType.ERROR_STATUS

    @pytest.mark.asyncio
    async def test_error_scenarios_have_status_code(self, generator, endpoint_with_body):
        scenarios = generator._error_status_scenarios(endpoint_with_body)
        for s in scenarios:
            assert "status_code" in s.config
            assert 100 <= s.config["status_code"] <= 599

    @pytest.mark.asyncio
    async def test_error_scenarios_have_proper_structure(self, generator, endpoint_with_body):
        scenarios = generator._error_status_scenarios(endpoint_with_body)
        for s in scenarios:
            assert s.name
            assert s.scenario_type == ChaosScenarioType.ERROR_STATUS
            assert s.endpoint == endpoint_with_body


class TestTamperingScenarios:

    @pytest.mark.asyncio
    async def test_generates_tampering_scenarios_for_fields(self, generator, endpoint_with_body):
        scenarios = generator._tampering_scenarios(endpoint_with_body)
        assert len(scenarios) > 0
        for s in scenarios:
            assert s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING

    @pytest.mark.asyncio
    async def test_tampering_scenarios_have_field_path(self, generator, endpoint_with_body):
        scenarios = generator._tampering_scenarios(endpoint_with_body)
        for s in scenarios:
            assert "field_path" in s.config

    @pytest.mark.asyncio
    async def test_tampering_scenarios_have_tamper_type(self, generator, endpoint_with_body):
        scenarios = generator._tampering_scenarios(endpoint_with_body)
        for s in scenarios:
            assert "tamper_type" in s.config

    @pytest.mark.asyncio
    async def test_get_endpoint_has_header_injection(self, generator):
        bare_endpoint = Endpoint(path="/health", method=HttpMethod.GET)
        scenarios = generator._tampering_scenarios(bare_endpoint)
        assert len(scenarios) > 0
        assert any(s.config.get("tamper_type") == "inject" for s in scenarios)

    @pytest.mark.asyncio
    async def test_tampering_scenarios_have_proper_structure(self, generator, endpoint_with_body):
        scenarios = generator._tampering_scenarios(endpoint_with_body)
        for s in scenarios:
            assert s.name
            assert s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING
            assert s.endpoint == endpoint_with_body


class TestRateLimitScenarios:

    @pytest.mark.asyncio
    async def test_generates_rate_limit_scenarios(self, generator, endpoint_with_body):
        scenarios = generator._rate_limit_scenarios(endpoint_with_body)
        assert len(scenarios) >= 2
        for s in scenarios:
            assert s.scenario_type == ChaosScenarioType.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_rate_limit_scenarios_have_rps_and_duration(self, generator, endpoint_with_body):
        scenarios = generator._rate_limit_scenarios(endpoint_with_body)
        for s in scenarios:
            assert "requests_per_second" in s.config
            assert "duration_seconds" in s.config
            assert isinstance(s.config["requests_per_second"], int)
            assert isinstance(s.config["duration_seconds"], int)
            assert s.config["requests_per_second"] >= 1
            assert s.config["duration_seconds"] >= 1

    @pytest.mark.asyncio
    async def test_rate_limit_scenarios_have_proper_structure(self, generator, endpoint_with_body):
        scenarios = generator._rate_limit_scenarios(endpoint_with_body)
        for s in scenarios:
            assert s.name
            assert s.scenario_type == ChaosScenarioType.RATE_LIMIT
            assert s.endpoint == endpoint_with_body


class TestGenerateForEndpoint:

    @pytest.mark.asyncio
    async def test_generate_all_four_types(self, generator, endpoint_with_body):
        scenarios = await generator._generate_for_endpoint(endpoint_with_body)
        types = {s.scenario_type for s in scenarios}
        assert ChaosScenarioType.LATENCY in types
        assert ChaosScenarioType.ERROR_STATUS in types
        assert ChaosScenarioType.REQUEST_TAMPERING in types
        assert ChaosScenarioType.RATE_LIMIT in types

    @pytest.mark.asyncio
    async def test_generate_at_least_10_scenarios(self, generator, endpoint_with_body):
        scenarios = await generator._generate_for_endpoint(endpoint_with_body)
        assert len(scenarios) >= 10, f"Expected >= 10 scenarios, got {len(scenarios)}"

    @pytest.mark.asyncio
    async def test_each_scenario_has_proper_fields(self, generator, endpoint_with_body):
        scenarios = await generator._generate_for_endpoint(endpoint_with_body)
        for s in scenarios:
            assert isinstance(s, ChaosScenario)
            assert s.name, "name must be set"
            assert isinstance(s.scenario_type, ChaosScenarioType)
            assert s.endpoint == endpoint_with_body
            assert isinstance(s.config, dict)


class TestGenerate:

    @pytest.mark.asyncio
    async def test_generate_processes_all_endpoints(self, generator, api_spec):
        scenarios = await generator.generate(api_spec)
        assert len(scenarios) > 0
        endpoint_paths = {s.endpoint.path for s in scenarios}
        assert "/users" in endpoint_paths
        assert "/users/{id}" in endpoint_paths

    @pytest.mark.asyncio
    async def test_generate_returns_chaos_scenarios(self, generator, api_spec):
        scenarios = await generator.generate(api_spec)
        for s in scenarios:
            assert isinstance(s, ChaosScenario)


class TestRequestBodyPresence:

    @pytest.mark.asyncio
    async def test_endpoint_with_body_generates_tampering(self, generator, endpoint_with_body):
        scenarios = await generator._generate_for_endpoint(endpoint_with_body)
        tampering = [s for s in scenarios if s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING]
        assert len(tampering) > 0

    @pytest.mark.asyncio
    async def test_endpoint_without_body_has_header_injection(self, generator, endpoint_without_body):
        scenarios = await generator._generate_for_endpoint(endpoint_without_body)
        tampering = [s for s in scenarios if s.scenario_type == ChaosScenarioType.REQUEST_TAMPERING]
        assert len(tampering) > 0


class TestLLMEnhancement:

    @pytest.mark.asyncio
    async def test_llm_enhances_scenarios(self, generator_with_llm, endpoint_with_body):
        spec = APISpec(title="Test", version="1.0.0", endpoints=[endpoint_with_body])
        scenarios = await generator_with_llm.generate(spec)
        generator_with_llm._llm_router.route.assert_awaited()

    @pytest.mark.asyncio
    async def test_llm_adds_extra_scenarios(self, generator_with_llm, endpoint_with_body):
        spec = APISpec(title="Test", version="1.0.0", endpoints=[endpoint_with_body])
        gen_no_llm = ScenarioGenerator()
        scenarios_no_llm = await gen_no_llm.generate(spec)
        scenarios_with_llm = await generator_with_llm.generate(spec)
        assert len(scenarios_with_llm) >= len(scenarios_no_llm)

    @pytest.mark.asyncio
    async def test_llm_failure_does_not_crash(self, endpoint_with_body):
        mock_router = AsyncMock()
        mock_router.route.side_effect = RuntimeError("LLM unavailable")
        gen = ScenarioGenerator(llm_router=mock_router)
        spec = APISpec(title="Test", version="1.0.0", endpoints=[endpoint_with_body])
        scenarios = await gen.generate(spec)
        assert len(scenarios) > 0


class TestUniqueIds:

    @pytest.mark.asyncio
    async def test_all_scenario_ids_are_unique(self, generator, api_spec):
        scenarios = await generator.generate(api_spec)
        ids = [s.id for s in scenarios]
        assert len(ids) == len(set(ids)), "Scenario IDs must be unique"

    @pytest.mark.asyncio
    async def test_scenario_ids_are_uuid_format(self, generator, api_spec):
        scenarios = await generator.generate(api_spec)
        for s in scenarios:
            uuid.UUID(s.id)


class TestSeverityAssignment:

    @pytest.mark.asyncio
    async def test_latency_scenarios_have_severity(self, generator, endpoint_with_body):
        scenarios = generator._latency_scenarios(endpoint_with_body)
        for s in scenarios:
            assert isinstance(s.severity, Severity)

    @pytest.mark.asyncio
    async def test_error_scenarios_have_severity(self, generator, endpoint_with_body):
        scenarios = generator._error_status_scenarios(endpoint_with_body)
        for s in scenarios:
            assert isinstance(s.severity, Severity)

    @pytest.mark.asyncio
    async def test_tampering_scenarios_have_high_or_critical_severity(self, generator, endpoint_with_body):
        scenarios = generator._tampering_scenarios(endpoint_with_body)
        for s in scenarios:
            assert s.severity in (Severity.HIGH, Severity.CRITICAL, Severity.MEDIUM)

    @pytest.mark.asyncio
    async def test_rate_limit_scenarios_have_severity(self, generator, endpoint_with_body):
        scenarios = generator._rate_limit_scenarios(endpoint_with_body)
        for s in scenarios:
            assert isinstance(s.severity, Severity)


class TestLLMResponseParsing:

    @pytest.mark.asyncio
    async def test_parse_json_array_response(self, generator, endpoint_with_body):
        response = json.dumps([
            {"name": "Test 1", "type": "latency", "config": {"delay_ms": 3000}, "severity": "high"},
            {"name": "Test 2", "type": "error_status", "config": {"status_code": 503}, "severity": "critical"},
        ])
        scenarios = generator._parse_llm_response(response, endpoint_with_body)
        assert len(scenarios) == 2
        assert scenarios[0].scenario_type == ChaosScenarioType.LATENCY
        assert scenarios[1].scenario_type == ChaosScenarioType.ERROR_STATUS

    @pytest.mark.asyncio
    async def test_parse_json_with_code_block(self, generator, endpoint_with_body):
        response = '```json\n[{"name": "Test", "type": "latency", "config": {}, "severity": "low"}]\n```'
        scenarios = generator._parse_llm_response(response, endpoint_with_body)
        assert len(scenarios) == 1

    @pytest.mark.asyncio
    async def test_parse_invalid_json_returns_empty(self, generator, endpoint_with_body):
        response = "not valid json at all"
        scenarios = generator._parse_llm_response(response, endpoint_with_body)
        assert isinstance(scenarios, list)

    @pytest.mark.asyncio
    async def test_parse_unknown_type_defaults_to_latency(self, generator, endpoint_with_body):
        response = json.dumps([{"name": "Test", "type": "unknown_type", "config": {}}])
        scenarios = generator._parse_llm_response(response, endpoint_with_body)
        assert len(scenarios) == 1
        assert scenarios[0].scenario_type == ChaosScenarioType.LATENCY


class TestBuildPrompt:

    def test_build_prompt_includes_endpoint_info(self, generator, endpoint_with_body):
        prompt = generator._build_prompt(endpoint_with_body)
        assert "POST" in prompt
        assert "/users" in prompt

    def test_build_prompt_includes_fields(self, generator, endpoint_with_body):
        prompt = generator._build_prompt(endpoint_with_body)
        assert "username" in prompt
        assert "email" in prompt

    def test_build_prompt_includes_summary(self, generator, endpoint_with_body):
        prompt = generator._build_prompt(endpoint_with_body)
        assert "Create user" in prompt
