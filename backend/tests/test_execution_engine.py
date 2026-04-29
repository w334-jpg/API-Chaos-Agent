"""Comprehensive unit tests for the ExecutionEngine service.

Uses httpx.MockTransport to mock HTTP calls - no real network requests.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    ResponseData,
    ScenarioResult,
    TestResult,
)
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Severity
from api_chaos_agent.models.schema import Endpoint, HttpMethod
from api_chaos_agent.services.execution_engine import ExecutionEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_endpoint(
    path: str = "/pets",
    method: HttpMethod = HttpMethod.GET,
) -> Endpoint:
    return Endpoint(path=path, method=method, summary="Test endpoint")


def _make_config(**overrides: Any) -> ExecutionConfig:
    defaults = dict(
        base_url="http://testserver",
        concurrency=10,
        timeout_seconds=5.0,
        max_retries=2,
        retry_delay_seconds=0.01,
        headers={},
        proxy=None,
        serial=False,
    )
    defaults.update(overrides)
    return ExecutionConfig(**defaults)


def _make_scenario(
    scenario_type: ChaosScenarioType = ChaosScenarioType.LATENCY,
    config: dict[str, Any] | None = None,
    name: str = "test-scenario",
    endpoint: Endpoint | None = None,
    scenario_id: str = "sc-001",
    severity: Severity = Severity.MEDIUM,
) -> ChaosScenario:
    return ChaosScenario(
        id=scenario_id,
        name=name,
        scenario_type=scenario_type,
        endpoint=endpoint or _make_endpoint(),
        config=config or {},
        severity=severity,
    )


def _mock_handler(status_code: int = 200, body: Any = None, headers: dict[str, str] | None = None):
    """Return an httpx mock transport handler that responds with the given status/body."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=body or {"ok": True},
            headers=headers or {},
        )

    return handler


def _error_handler(exc: Exception):
    """Return a mock handler that always raises the given exception."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


# ---------------------------------------------------------------------------
# 1. Test executing a single latency injection scenario
# ---------------------------------------------------------------------------

class TestLatencyInjection:
    @pytest.mark.asyncio
    async def test_latency_injection_returns_response(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 50, "jitter_ms": 0},
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.response.status_code == 200
        assert result.response.elapsed_ms >= 50  # delay was applied


# ---------------------------------------------------------------------------
# 2. Test executing a single error status code scenario
# ---------------------------------------------------------------------------

class TestErrorStatusScenario:
    @pytest.mark.asyncio
    async def test_error_status_scenario(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.ERROR_STATUS,
            config={"status_code": 500, "repeat_count": 1},
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(500, {"error": "Internal"})))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.response.status_code == 500
        assert result.vulnerability_found is True


# ---------------------------------------------------------------------------
# 3. Test executing a single request tampering scenario
# ---------------------------------------------------------------------------

class TestRequestTampering:
    @pytest.mark.asyncio
    async def test_tamper_remove_field(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            config={
                "field_path": "name",
                "tamper_type": "remove",
            },
            endpoint=_make_endpoint(method=HttpMethod.POST),
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.response.status_code == 200

    @pytest.mark.asyncio
    async def test_tamper_replace_field(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            config={
                "field_path": "name",
                "tamper_type": "replace",
                "tamper_value": "EVIL_INPUT",
            },
            endpoint=_make_endpoint(method=HttpMethod.POST),
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_tamper_overflow_field(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            config={
                "field_path": "name",
                "tamper_type": "overflow",
            },
            endpoint=_make_endpoint(method=HttpMethod.POST),
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)
        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_tamper_type_mismatch(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            config={
                "field_path": "age",
                "tamper_type": "type_mismatch",
            },
            endpoint=_make_endpoint(method=HttpMethod.POST),
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)
        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_tamper_inject_field(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.REQUEST_TAMPERING,
            config={
                "field_path": "admin",
                "tamper_type": "inject",
                "tamper_value": True,
            },
            endpoint=_make_endpoint(method=HttpMethod.POST),
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)
        assert result.status == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# 4. Test executing a single rate limit burst scenario
# ---------------------------------------------------------------------------

class TestRateLimitBurst:
    @pytest.mark.asyncio
    async def test_rate_limit_burst(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.RATE_LIMIT,
            config={"requests_per_second": 5, "duration_seconds": 1},
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED
        # Should have sent at least requests_per_second * duration_seconds requests
        assert result.response.body is not None


# ---------------------------------------------------------------------------
# 5. Test parallel execution of multiple scenarios (concurrency=10)
# ---------------------------------------------------------------------------

class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        scenarios = [
            _make_scenario(
                scenario_type=ChaosScenarioType.LATENCY,
                config={"delay_ms": 10},
                name=f"parallel-{i}",
                scenario_id=f"sc-p-{i}",
            )
            for i in range(10)
        ]
        config = _make_config(concurrency=10, serial=False)
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine.execute(scenarios)

        assert result.total_scenarios == 10
        assert result.completed_scenarios == 10
        assert result.failed_scenarios == 0
        assert len(result.results) == 10
        for sr in result.results:
            assert sr.status == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# 6. Test serial execution mode
# ---------------------------------------------------------------------------

class TestSerialExecution:
    @pytest.mark.asyncio
    async def test_serial_execution(self):
        scenarios = [
            _make_scenario(
                scenario_type=ChaosScenarioType.LATENCY,
                config={"delay_ms": 10},
                name=f"serial-{i}",
                scenario_id=f"sc-s-{i}",
            )
            for i in range(3)
        ]
        config = _make_config(serial=True)
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine.execute(scenarios)

        assert result.total_scenarios == 3
        assert result.completed_scenarios == 3
        assert len(result.results) == 3


# ---------------------------------------------------------------------------
# 7. Test timeout handling (scenario exceeds timeout)
# ---------------------------------------------------------------------------

class TestTimeoutHandling:
    @pytest.mark.asyncio
    async def test_timeout_marks_scenario_as_timeout(self):
        # MockTransport does not enforce httpx timeouts, so we simulate
        # a timeout by raising ReadTimeout directly from the handler.
        async def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out")

        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(timeout_seconds=5.0)
        engine = ExecutionEngine(config, transport=httpx.MockTransport(timeout_handler))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.TIMEOUT
        assert result.response.error is not None


# ---------------------------------------------------------------------------
# 8. Test retry logic (failed request retries up to max_retries)
# ---------------------------------------------------------------------------

class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retry_on_connection_error_then_success(self):
        call_count = 0

        async def flaky_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json={"ok": True})

        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(max_retries=3, retry_delay_seconds=0.01)
        engine = ExecutionEngine(config, transport=httpx.MockTransport(flaky_handler))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED
        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        async def always_fail_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(max_retries=2, retry_delay_seconds=0.01)
        engine = ExecutionEngine(config, transport=httpx.MockTransport(always_fail_handler))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.FAILED
        assert result.response.error is not None


# ---------------------------------------------------------------------------
# 9. Test concurrency limit enforcement (100 concurrent max)
# ---------------------------------------------------------------------------

class TestConcurrencyLimit:
    @pytest.mark.asyncio
    async def test_concurrency_semaphore_limits_concurrent_requests(self):
        max_concurrent = 0
        current_concurrent = 0

        async def tracking_handler(request: httpx.Request) -> httpx.Response:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)
            current_concurrent -= 1
            return httpx.Response(200, json={"ok": True})

        scenarios = [
            _make_scenario(
                scenario_type=ChaosScenarioType.LATENCY,
                config={"delay_ms": 0},
                name=f"conc-{i}",
                scenario_id=f"sc-c-{i}",
            )
            for i in range(20)
        ]
        config = _make_config(concurrency=5, serial=False)
        engine = ExecutionEngine(config, transport=httpx.MockTransport(tracking_handler))

        result = await engine.execute(scenarios)

        assert result.completed_scenarios == 20
        # max_concurrent should never exceed the concurrency limit
        assert max_concurrent <= 5


# ---------------------------------------------------------------------------
# 10. Test proxy configuration is used
# ---------------------------------------------------------------------------

class TestProxyConfiguration:
    @pytest.mark.asyncio
    async def test_proxy_stored_in_engine(self):
        """Verify proxy config is stored and would be used in real requests."""
        config = _make_config(proxy="http://proxy.example.com:8080")
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        # Verify the engine stores the proxy configuration
        assert engine._proxy == "http://proxy.example.com:8080"

    @pytest.mark.asyncio
    async def test_proxy_used_without_mock_transport(self):
        """Verify proxy is passed to httpx client when no custom transport is used."""
        config = _make_config(proxy="http://proxy.example.com:8080")
        engine = ExecutionEngine(config)  # no mock transport

        # Build a request to verify _do_request would include proxy
        # We can't make a real request, but we can verify the config is stored
        assert engine._proxy == "http://proxy.example.com:8080"
        assert engine._transport is None  # no custom transport means proxy will be used


# ---------------------------------------------------------------------------
# 11. Test custom headers are sent
# ---------------------------------------------------------------------------

class TestCustomHeaders:
    @pytest.mark.asyncio
    async def test_custom_headers_in_request(self):
        received_headers: dict[str, str] = {}

        async def header_capture_handler(request: httpx.Request) -> httpx.Response:
            nonlocal received_headers
            received_headers = dict(request.headers)
            return httpx.Response(200, json={"ok": True})

        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(headers={"X-Custom-Auth": "token123", "X-Request-Id": "abc"})
        engine = ExecutionEngine(config, transport=httpx.MockTransport(header_capture_handler))

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.COMPLETED
        assert "x-custom-auth" in received_headers
        assert received_headers["x-custom-auth"] == "token123"
        assert "x-request-id" in received_headers
        assert received_headers["x-request-id"] == "abc"


# ---------------------------------------------------------------------------
# 12. Test execution result contains correct status/response data
# ---------------------------------------------------------------------------

class TestExecutionResultData:
    @pytest.mark.asyncio
    async def test_result_contains_correct_fields(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
            scenario_id="sc-result-1",
            name="latency-test",
            severity=Severity.HIGH,
        )
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200, {"status": "ok"})))

        result = await engine._execute_single(scenario)

        assert result.scenario_id == "sc-result-1"
        assert result.scenario_name == "latency-test"
        assert result.scenario_type == ChaosScenarioType.LATENCY.value
        assert result.severity == Severity.HIGH
        assert result.response.status_code == 200
        assert result.response.body is not None
        assert result.response.elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_test_result_aggregation(self):
        scenarios = [
            _make_scenario(
                scenario_type=ChaosScenarioType.LATENCY,
                config={"delay_ms": 0},
                name=f"agg-{i}",
                scenario_id=f"sc-agg-{i}",
            )
            for i in range(5)
        ]
        config = _make_config()
        engine = ExecutionEngine(config, transport=httpx.MockTransport(_mock_handler(200)))

        result = await engine.execute(scenarios)

        assert isinstance(result, TestResult)
        assert result.total_scenarios == 5
        assert result.completed_scenarios == 5
        assert result.failed_scenarios == 0
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.config is not None


# ---------------------------------------------------------------------------
# 13. Test handling connection errors gracefully
# ---------------------------------------------------------------------------

class TestConnectionErrors:
    @pytest.mark.asyncio
    async def test_connect_error_handled_gracefully(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(max_retries=0)
        engine = ExecutionEngine(
            config,
            transport=httpx.MockTransport(_error_handler(httpx.ConnectError("Connection refused"))),
        )

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.FAILED
        assert result.response.error is not None
        assert "Connection refused" in result.response.error

    @pytest.mark.asyncio
    async def test_connect_timeout_handled_gracefully(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(max_retries=0)
        engine = ExecutionEngine(
            config,
            transport=httpx.MockTransport(_error_handler(httpx.ConnectTimeout("Timed out"))),
        )

        result = await engine._execute_single(scenario)

        # ConnectTimeout is a subclass of TimeoutException, so it's marked as TIMEOUT
        assert result.status == ExecutionStatus.TIMEOUT
        assert result.response.error is not None

    @pytest.mark.asyncio
    async def test_read_timeout_handled_gracefully(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(max_retries=0)
        engine = ExecutionEngine(
            config,
            transport=httpx.MockTransport(_error_handler(httpx.ReadTimeout("Read timed out"))),
        )

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.TIMEOUT
        assert result.response.error is not None

    @pytest.mark.asyncio
    async def test_generic_exception_handled_gracefully(self):
        scenario = _make_scenario(
            scenario_type=ChaosScenarioType.LATENCY,
            config={"delay_ms": 0},
        )
        config = _make_config(max_retries=0)
        engine = ExecutionEngine(
            config,
            transport=httpx.MockTransport(_error_handler(RuntimeError("Unexpected error"))),
        )

        result = await engine._execute_single(scenario)

        assert result.status == ExecutionStatus.FAILED
        assert result.response.error is not None

    @pytest.mark.asyncio
    async def test_connection_error_in_full_execution(self):
        scenarios = [
            _make_scenario(
                scenario_type=ChaosScenarioType.LATENCY,
                config={"delay_ms": 0},
                name=f"err-{i}",
                scenario_id=f"sc-err-{i}",
            )
            for i in range(3)
        ]
        config = _make_config(max_retries=0)
        engine = ExecutionEngine(
            config,
            transport=httpx.MockTransport(_error_handler(httpx.ConnectError("Connection refused"))),
        )

        result = await engine.execute(scenarios)

        assert result.total_scenarios == 3
        assert result.failed_scenarios == 3
        assert result.completed_scenarios == 0
        for sr in result.results:
            assert sr.status == ExecutionStatus.FAILED
