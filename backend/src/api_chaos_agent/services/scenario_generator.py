"""Scenario Generator — generates chaos test scenarios from API specs.

Uses the LLM router for intelligent scenario generation and falls back
to rule-based generation when LLM is unavailable.
"""

from __future__ import annotations

import json
import uuid

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.scenario import (
    ChaosScenario,
    ChaosScenarioType,
    Severity,
)
from api_chaos_agent.models.schema import APISpec, Endpoint, FieldConstraint, FieldType, HttpMethod
from api_chaos_agent.services.llm_router import LLMRouter, TaskComplexity

logger = get_logger(__name__)


class ScenarioGenerator:
    """Generate chaos test scenarios from an API specification."""

    def __init__(self, llm_router: LLMRouter | None = None) -> None:
        self._llm_router = llm_router or LLMRouter()

    async def generate(self, spec: APISpec) -> list[ChaosScenario]:
        scenarios: list[ChaosScenario] = []
        for endpoint in spec.endpoints:
            scenarios.extend(await self._generate_for_endpoint(endpoint))
        for s in scenarios:
            if not s.id:
                s.id = str(uuid.uuid4())
        return scenarios

    async def _generate_for_endpoint(self, endpoint: Endpoint) -> list[ChaosScenario]:
        scenarios: list[ChaosScenario] = []

        scenarios.extend(self._latency_scenarios(endpoint))
        scenarios.extend(self._error_status_scenarios(endpoint))
        scenarios.extend(self._tampering_scenarios(endpoint))
        scenarios.extend(self._rate_limit_scenarios(endpoint))

        try:
            llm_scenarios = await self._generate_llm_scenarios(endpoint)
            scenarios.extend(llm_scenarios)
        except Exception as exc:
            logger.warning(
                "LLM scenario generation failed for %s %s: %s",
                endpoint.method.value,
                endpoint.path,
                exc,
            )

        return scenarios

    def _latency_scenarios(self, endpoint: Endpoint) -> list[ChaosScenario]:
        return [
            ChaosScenario(
                name=f"Low Latency - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.LATENCY,
                endpoint=endpoint,
                description=f"Inject low latency into {endpoint.method.value} {endpoint.path}",
                config={"delay_ms": 500, "jitter_ms": 100},
                expected_behavior="API should handle minor delays gracefully",
                severity=Severity.LOW,
            ),
            ChaosScenario(
                name=f"Medium Latency - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.LATENCY,
                endpoint=endpoint,
                description=f"Inject medium latency into {endpoint.method.value} {endpoint.path}",
                config={"delay_ms": 2000, "jitter_ms": 500},
                expected_behavior="API should handle delayed responses with appropriate timeout",
                severity=Severity.MEDIUM,
            ),
            ChaosScenario(
                name=f"High Latency - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.LATENCY,
                endpoint=endpoint,
                description=f"Inject high latency into {endpoint.method.value} {endpoint.path} to test timeout handling",
                config={"delay_ms": 5000, "jitter_ms": 1000},
                expected_behavior="API should timeout gracefully without hanging",
                severity=Severity.HIGH,
            ),
        ]

    def _error_status_scenarios(self, endpoint: Endpoint) -> list[ChaosScenario]:
        return [
            ChaosScenario(
                name=f"Server Error 500 - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.ERROR_STATUS,
                endpoint=endpoint,
                description=f"Test {endpoint.method.value} {endpoint.path} with 500 Internal Server Error",
                config={"status_code": 500, "repeat_count": 1},
                expected_behavior="API should return appropriate error response without crashing",
                severity=Severity.MEDIUM,
            ),
            ChaosScenario(
                name=f"Bad Gateway 502 - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.ERROR_STATUS,
                endpoint=endpoint,
                description=f"Test {endpoint.method.value} {endpoint.path} with 502 Bad Gateway",
                config={"status_code": 502, "repeat_count": 1},
                expected_behavior="API should handle upstream failures gracefully",
                severity=Severity.MEDIUM,
            ),
            ChaosScenario(
                name=f"Service Unavailable 503 - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.ERROR_STATUS,
                endpoint=endpoint,
                description=f"Test {endpoint.method.value} {endpoint.path} with 503 Service Unavailable",
                config={"status_code": 503, "repeat_count": 1},
                expected_behavior="API should handle service unavailability with retry logic",
                severity=Severity.HIGH,
            ),
            ChaosScenario(
                name=f"Too Many Requests 429 - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.ERROR_STATUS,
                endpoint=endpoint,
                description=f"Test {endpoint.method.value} {endpoint.path} with 429 Too Many Requests",
                config={"status_code": 429, "repeat_count": 1},
                expected_behavior="API client should respect rate limit headers and back off",
                severity=Severity.LOW,
            ),
        ]

    def _tampering_scenarios(self, endpoint: Endpoint) -> list[ChaosScenario]:
        scenarios: list[ChaosScenario] = []

        if endpoint.method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
            if endpoint.request_body and endpoint.request_body.fields:
                for field in endpoint.request_body.fields:
                    scenarios.extend(self._field_tampering_scenarios(endpoint, field))
            else:
                scenarios.append(self._generic_tampering_scenario(endpoint))

        if endpoint.parameters:
            for param in endpoint.parameters:
                scenarios.append(
                    ChaosScenario(
                        name=f"Param Tampering - {endpoint.method.value} {endpoint.path} ({param.name})",
                        scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                        endpoint=endpoint,
                        description=f"Tamper parameter '{param.name}' in {endpoint.method.value} {endpoint.path}",
                        config={
                            "field_path": param.name,
                            "tamper_type": "invalid_value",
                            "tamper_value": None,
                        },
                        expected_behavior="API should validate and reject invalid parameter values",
                        severity=Severity.HIGH,
                    )
                )

        if not scenarios:
            scenarios.append(
                ChaosScenario(
                    name=f"Header Injection - {endpoint.method.value} {endpoint.path}",
                    scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                    endpoint=endpoint,
                    description=f"Inject malicious headers into {endpoint.method.value} {endpoint.path}",
                    config={
                        "field_path": "X-Custom-Header",
                        "tamper_type": "inject",
                        "tamper_value": "<script>alert(1)</script>",
                    },
                    expected_behavior="API should sanitize or reject malicious header values",
                    severity=Severity.HIGH,
                )
            )

        return scenarios

    def _field_tampering_scenarios(
        self, endpoint: Endpoint, field: FieldConstraint
    ) -> list[ChaosScenario]:
        scenarios: list[ChaosScenario] = []

        scenarios.append(
            ChaosScenario(
                name=f"Type Mismatch - {endpoint.method.value} {endpoint.path} ({field.field_name})",
                scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                endpoint=endpoint,
                description=f"Send wrong type for field '{field.field_name}' in {endpoint.method.value} {endpoint.path}",
                config={
                    "field_path": field.field_name,
                    "tamper_type": "type_mismatch",
                    "tamper_value": None,
                },
                expected_behavior="API should validate input types and reject type mismatches",
                severity=Severity.HIGH,
            )
        )

        if field.field_type == FieldType.STRING:
            scenarios.append(
                ChaosScenario(
                    name=f"Overflow - {endpoint.method.value} {endpoint.path} ({field.field_name})",
                    scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                    endpoint=endpoint,
                    description=f"Send oversized value for field '{field.field_name}'",
                    config={
                        "field_path": field.field_name,
                        "tamper_type": "overflow",
                        "tamper_value": "A" * 10000,
                    },
                    expected_behavior="API should enforce length limits and reject oversized inputs",
                    severity=Severity.HIGH,
                )
            )

        if field.field_type in (FieldType.INTEGER, FieldType.NUMBER):
            scenarios.append(
                ChaosScenario(
                    name=f"Boundary Value - {endpoint.method.value} {endpoint.path} ({field.field_name})",
                    scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                    endpoint=endpoint,
                    description=f"Send boundary value for field '{field.field_name}'",
                    config={
                        "field_path": field.field_name,
                        "tamper_type": "boundary",
                        "tamper_value": -999999999,
                    },
                    expected_behavior="API should enforce range limits and reject out-of-bound values",
                    severity=Severity.MEDIUM,
                )
            )

        if field.enum_values:
            scenarios.append(
                ChaosScenario(
                    name=f"Invalid Enum - {endpoint.method.value} {endpoint.path} ({field.field_name})",
                    scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                    endpoint=endpoint,
                    description=f"Send invalid enum value for field '{field.field_name}'",
                    config={
                        "field_path": field.field_name,
                        "tamper_type": "enum_violation",
                        "tamper_value": "INVALID_ENUM_VALUE",
                    },
                    expected_behavior="API should reject values not in the allowed enum list",
                    severity=Severity.HIGH,
                )
            )

        if field.required:
            scenarios.append(
                ChaosScenario(
                    name=f"Missing Required - {endpoint.method.value} {endpoint.path} ({field.field_name})",
                    scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                    endpoint=endpoint,
                    description=f"Omit required field '{field.field_name}' from request",
                    config={
                        "field_path": field.field_name,
                        "tamper_type": "missing",
                        "tamper_value": None,
                    },
                    expected_behavior="API should reject requests missing required fields",
                    severity=Severity.CRITICAL,
                )
            )

        if field.format in ("email", "uri", "date-time"):
            scenarios.append(
                ChaosScenario(
                    name=f"Invalid Format - {endpoint.method.value} {endpoint.path} ({field.field_name})",
                    scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
                    endpoint=endpoint,
                    description=f"Send malformed {field.format} for field '{field.field_name}'",
                    config={
                        "field_path": field.field_name,
                        "tamper_type": "format_violation",
                        "tamper_value": "not-a-valid-format",
                    },
                    expected_behavior=f"API should reject malformed {field.format} values",
                    severity=Severity.HIGH,
                )
            )

        return scenarios

    def _generic_tampering_scenario(self, endpoint: Endpoint) -> ChaosScenario:
        return ChaosScenario(
            name=f"Body Overflow - {endpoint.method.value} {endpoint.path}",
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            endpoint=endpoint,
            description=f"Send oversized body to {endpoint.method.value} {endpoint.path}",
            config={"field_path": "body", "tamper_type": "overflow", "tamper_value": None},
            expected_behavior="API should enforce payload size limits",
            severity=Severity.HIGH,
        )

    def _rate_limit_scenarios(self, endpoint: Endpoint) -> list[ChaosScenario]:
        return [
            ChaosScenario(
                name=f"Burst Requests - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.RATE_LIMIT,
                endpoint=endpoint,
                description=f"Burst requests to {endpoint.method.value} {endpoint.path} to test rate limiting",
                config={"requests_per_second": 50, "duration_seconds": 5},
                expected_behavior="API should rate limit excessive requests with 429 status",
                severity=Severity.MEDIUM,
            ),
            ChaosScenario(
                name=f"Sustained Load - {endpoint.method.value} {endpoint.path}",
                scenario_type=ChaosScenarioType.RATE_LIMIT,
                endpoint=endpoint,
                description=f"Sustained moderate load on {endpoint.method.value} {endpoint.path}",
                config={"requests_per_second": 10, "duration_seconds": 10},
                expected_behavior="API should handle sustained load without degradation",
                severity=Severity.LOW,
            ),
        ]

    async def _generate_llm_scenarios(self, endpoint: Endpoint) -> list[ChaosScenario]:
        scenarios: list[ChaosScenario] = []

        prompt = self._build_prompt(endpoint)
        try:
            response = await self._llm_router.route(
                prompt=prompt,
                system_prompt="You are a chaos testing expert. Generate creative test scenarios.",
                complexity=TaskComplexity.MEDIUM,
            )
            parsed = self._parse_llm_response(response, endpoint)
            scenarios.extend(parsed)
        except Exception as exc:
            logger.warning("LLM scenario generation failed: %s", exc)

        return scenarios

    def _build_prompt(self, endpoint: Endpoint) -> str:
        parts = [
            f"Generate chaos test scenarios for the endpoint: {endpoint.method.value} {endpoint.path}",
        ]
        if endpoint.summary:
            parts.append(f"Summary: {endpoint.summary}")
        if endpoint.parameters:
            param_names = [p.name for p in endpoint.parameters]
            parts.append(f"Parameters: {', '.join(param_names)}")
        if endpoint.request_body and endpoint.request_body.fields:
            field_names = [f.field_name for f in endpoint.request_body.fields]
            parts.append(f"Request fields: {', '.join(field_names)}")

        parts.append(
            "Return scenarios as JSON array with fields: name, type (latency|error_status|request_tampering|rate_limit), config, severity (critical|high|medium|low|info)"
        )
        return " | ".join(parts)

    def _parse_llm_response(self, response: str, endpoint: Endpoint) -> list[ChaosScenario]:
        scenarios: list[ChaosScenario] = []
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            items = json.loads(json_str)
            if not isinstance(items, list):
                items = [items]

            for item in items:
                if not isinstance(item, dict):
                    continue
                scenario_type_str = item.get("type", "latency")
                try:
                    scenario_type = ChaosScenarioType(scenario_type_str)
                except ValueError:
                    scenario_type = ChaosScenarioType.LATENCY

                severity_str = item.get("severity", "medium")
                try:
                    severity = Severity(severity_str)
                except ValueError:
                    severity = Severity.MEDIUM

                scenario = ChaosScenario(
                    name=item.get(
                        "name", f"LLM Generated - {endpoint.method.value} {endpoint.path}"
                    ),
                    scenario_type=scenario_type,
                    endpoint=endpoint,
                    description=item.get("description", ""),
                    config=item.get("config", {}),
                    severity=severity,
                )
                scenarios.append(scenario)
        except (json.JSONDecodeError, IndexError, KeyError) as exc:
            logger.warning("Failed to parse LLM response: %s", exc)

        return scenarios
