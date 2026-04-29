"""Unit tests for ExecutionEngine."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from api_chaos_agent.models.report import ExecutionConfig, ExecutionStatus
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Severity
from api_chaos_agent.models.schema import Endpoint, HttpMethod
from api_chaos_agent.services.execution_engine import ExecutionEngine


def _make_endpoint(path: str = "/test", method: HttpMethod = HttpMethod.GET) -> Endpoint:
    return Endpoint(path=path, method=method, summary="Test endpoint")


def _make_scenario(
    scenario_type: ChaosScenarioType = ChaosScenarioType.LATENCY,
    endpoint: Endpoint | None = None,
    config: dict[str, Any] | None = None,
) -> ChaosScenario:
    return ChaosScenario(
        name="Test Scenario",
        scenario_type=scenario_type,
        endpoint=endpoint or _make_endpoint(),
        config=config or {"delay_ms": 0},
        severity=Severity.LOW,
    )


class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, status_code: int = 200, response_body: Any = None) -> None:
        self._status_code = status_code
        self._response_body = response_body or {"status": "ok"}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=self._status_code,
            json=self._response_body,
            headers={"content-type": "application/json"},
        )


@pytest.mark.asyncio
async def test_execute_single_latency() -> None:
    transport = MockTransport(200, {"result": "success"})
    config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
    engine = ExecutionEngine(config=config, transport=transport)

    scenario = _make_scenario(ChaosScenarioType.LATENCY, config={"delay_ms": 0, "jitter_ms": 0})
    result = await engine.execute([scenario])

    assert result.total_scenarios == 1
    assert result.completed_scenarios == 1
    assert result.failed_scenarios == 0


@pytest.mark.asyncio
async def test_execute_error_status() -> None:
    transport = MockTransport(500, {"error": "internal"})
    config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
    engine = ExecutionEngine(config=config, transport=transport)

    scenario = _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500})
    result = await engine.execute([scenario])

    assert result.total_scenarios == 1
    assert result.results[0].status == ExecutionStatus.COMPLETED


@pytest.mark.asyncio
async def test_execute_tampering() -> None:
    transport = MockTransport(200, {"received": True})
    endpoint = _make_endpoint("/data", HttpMethod.POST)
    config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
    engine = ExecutionEngine(config=config, transport=transport)

    scenario = _make_scenario(
        ChaosScenarioType.REQUEST_TAMPERING,
        endpoint=endpoint,
        config={"field_path": "name", "tamper_type": "remove"},
    )
    result = await engine.execute([scenario])
    assert result.completed_scenarios == 1


@pytest.mark.asyncio
async def test_execute_rate_limit() -> None:
    transport = MockTransport(200, {"ok": True})
    config = ExecutionConfig(base_url="http://testserver", concurrency=5, timeout_seconds=5.0)
    engine = ExecutionEngine(config=config, transport=transport)

    scenario = _make_scenario(
        ChaosScenarioType.RATE_LIMIT,
        config={"requests_per_second": 2, "duration_seconds": 1},
    )
    result = await engine.execute([scenario])
    assert result.total_scenarios == 1


@pytest.mark.asyncio
async def test_execute_serial() -> None:
    transport = MockTransport(200)
    config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0, serial=True)
    engine = ExecutionEngine(config=config, transport=transport)

    scenarios = [_make_scenario(ChaosScenarioType.LATENCY, config={"delay_ms": 0}) for _ in range(3)]
    result = await engine.execute(scenarios)
    assert result.completed_scenarios == 3


@pytest.mark.asyncio
async def test_execute_connection_error() -> None:
    class FailingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

    config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0, max_retries=0)
    engine = ExecutionEngine(config=config, transport=FailingTransport())

    scenario = _make_scenario(ChaosScenarioType.ERROR_STATUS, config={"status_code": 500})
    result = await engine.execute([scenario])
    assert result.failed_scenarios == 1


@pytest.mark.asyncio
async def test_build_default_body() -> None:
    from api_chaos_agent.models.schema import FieldConstraint, FieldType, RequestBody

    endpoint = Endpoint(
        path="/test",
        method=HttpMethod.POST,
        request_body=RequestBody(
            fields=[
                FieldConstraint(field_name="name", field_type=FieldType.STRING),
                FieldConstraint(field_name="age", field_type=FieldType.INTEGER),
            ]
        ),
    )
    body = ExecutionEngine._build_default_body(endpoint)
    assert body["name"] == "test_string"
    assert body["age"] == 42


@pytest.mark.asyncio
async def test_detect_vulnerability_rate_limit() -> None:
    from api_chaos_agent.models.report import ResponseData

    scenario = _make_scenario(ChaosScenarioType.RATE_LIMIT)
    response = ResponseData(status_code=200, body={"rate_limited": False})
    assert ExecutionEngine._detect_vulnerability(scenario, response) is True

    response2 = ResponseData(status_code=200, body={"rate_limited": True})
    assert ExecutionEngine._detect_vulnerability(scenario, response2) is False


@pytest.mark.asyncio
async def test_backoff_calculation() -> None:
    config = ExecutionConfig(base_url="http://testserver", concurrency=1, timeout_seconds=5.0)
    engine = ExecutionEngine(config=config, transport=MockTransport())

    for attempt in range(5):
        delay = engine._calculate_backoff(attempt)
        assert delay >= 0
        assert delay <= settings.execution.backoff_max + settings.execution.backoff_max * settings.execution.jitter_factor


from api_chaos_agent.core.config import settings
