"""Execution Engine service for API Chaos Agent.

Executes chaos test scenarios against target APIs with support for:
- Latency injection
- Error status code testing
- Request tampering
- Rate limit burst testing
- Parallel and serial execution modes
- Concurrency control via semaphore
- Exponential backoff retry logic with jitter
- Timeout handling
- Connection pooling via reusable httpx.AsyncClient
"""

from __future__ import annotations

import asyncio
import copy
import random
import time
from typing import Any

import httpx

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.report import (
    ExecutionConfig,
    ExecutionStatus,
    ResponseData,
    ScenarioResult,
    TestResult,
)
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType
from api_chaos_agent.models.schema import Endpoint, FieldType, HttpMethod


class ExecutionEngine:
    """Execute chaos test scenarios against a target API."""

    _logger = get_logger(__name__)

    def __init__(
        self,
        config: ExecutionConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._proxy: str | None = config.proxy
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._client: httpx.AsyncClient | None = None
        self._exec_cfg = settings.execution

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            client_kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self._config.timeout_seconds),
                "limits": httpx.Limits(
                    max_connections=self._config.concurrency,
                    max_keepalive_connections=max(1, self._config.concurrency // 2),
                    keepalive_expiry=60.0,
                ),
            }
            if self._transport is not None:
                client_kwargs["transport"] = self._transport
            elif self._proxy:
                client_kwargs["proxy"] = self._proxy
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def execute(self, scenarios: list[ChaosScenario]) -> TestResult:
        test_result = TestResult(
            total_scenarios=len(scenarios),
            config=self._config,
        )

        try:
            if self._config.serial:
                results = []
                for scenario in scenarios:
                    sr = await self._execute_single(scenario)
                    results.append(sr)
            else:
                results = await self._execute_parallel(scenarios)

            completed = 0
            failed = 0
            for sr in results:
                if sr.status == ExecutionStatus.COMPLETED:
                    completed += 1
                else:
                    failed += 1

            test_result.results = results
            test_result.completed_scenarios = completed
            test_result.failed_scenarios = failed
            test_result.completed_at = test_result.started_at.__class__.now()
        finally:
            await self.close()

        return test_result

    async def _execute_single(self, scenario: ChaosScenario) -> ScenarioResult:
        sr = ScenarioResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type.value,
            severity=scenario.severity,
        )

        try:
            if scenario.scenario_type == ChaosScenarioType.LATENCY:
                response = await self._inject_latency(scenario)
            elif scenario.scenario_type == ChaosScenarioType.ERROR_STATUS:
                response = await self._inject_error(scenario)
            elif scenario.scenario_type == ChaosScenarioType.REQUEST_TAMPERING:
                response = await self._tamper_request(scenario)
            elif scenario.scenario_type == ChaosScenarioType.RATE_LIMIT:
                response = await self._burst_requests(scenario)
            else:
                sr.status = ExecutionStatus.FAILED
                sr.response = ResponseData(error=f"Unknown scenario type: {scenario.scenario_type}")
                return sr

            sr.response = response
            sr.status = ExecutionStatus.COMPLETED

            sr.vulnerability_found = self._detect_vulnerability(scenario, response)
            sr.details = self._build_details(scenario, response)

        except httpx.TimeoutException as exc:
            sr.status = ExecutionStatus.TIMEOUT
            sr.response = ResponseData(error=str(exc))
            self._logger.warning("execution_timeout", scenario=scenario.name, error=str(exc))
        except httpx.ConnectError as exc:
            sr.status = ExecutionStatus.FAILED
            sr.response = ResponseData(error=str(exc))
            self._logger.warning(
                "execution_connection_error", scenario=scenario.name, error=str(exc)
            )
        except Exception as exc:
            sr.status = ExecutionStatus.FAILED
            sr.response = ResponseData(error=str(exc))
            self._logger.exception("execution_unexpected_error", scenario=scenario.name)
        finally:
            if scenario.scenario_type != ChaosScenarioType.RATE_LIMIT:
                await self.close()

        return sr

    async def _inject_latency(self, scenario: ChaosScenario) -> ResponseData:
        delay_ms = scenario.config.get("delay_ms", 0)
        jitter_ms = scenario.config.get("jitter_ms", 0)
        total_delay = min(
            (delay_ms + random.randint(0, max(jitter_ms, 0))) / 1000.0,
            self._exec_cfg.max_delay_seconds,
        )

        start = time.monotonic()
        if total_delay > 0:
            await asyncio.sleep(total_delay)

        response = await self._send_with_retry(scenario)
        total_elapsed = (time.monotonic() - start) * 1000
        response.elapsed_ms = round(total_elapsed, 2)
        return response

    async def _inject_error(self, scenario: ChaosScenario) -> ResponseData:
        return await self._send_with_retry(scenario)

    async def _tamper_request(self, scenario: ChaosScenario) -> ResponseData:
        return await self._send_with_retry(scenario, tamper=True)

    async def _burst_requests(self, scenario: ChaosScenario) -> ResponseData:
        rps = scenario.config.get("requests_per_second", 1)
        duration = scenario.config.get("duration_seconds", 1)
        total_requests = min(rps * duration, self._exec_cfg.max_burst_requests)

        status_codes: list[int] = []
        last_response: ResponseData | None = None
        errors: list[str] = []

        burst_semaphore = asyncio.Semaphore(min(rps, self._config.concurrency))

        async def _single_burst_request(idx: int) -> None:
            nonlocal last_response
            try:
                async with burst_semaphore:
                    resp = await self._send_with_retry(scenario)
                    if resp.status_code is not None:
                        status_codes.append(resp.status_code)
                    last_response = resp
            except Exception as exc:
                errors.append(str(exc))
            if idx < total_requests - 1 and rps > 0:
                await asyncio.sleep(min(1.0 / rps, 0.1))

        batch_size = min(rps, self._config.concurrency)
        for batch_start in range(0, total_requests, batch_size):
            batch_end = min(batch_start + batch_size, total_requests)
            tasks = [_single_burst_request(i) for i in range(batch_start, batch_end)]
            await asyncio.gather(*tasks, return_exceptions=True)

        if last_response is None:
            return ResponseData(error="; ".join(errors) if errors else "No responses received")

        last_response.body = {
            "total_requests": total_requests,
            "status_codes": status_codes,
            "errors": errors,
            "rate_limited": any(sc == 429 for sc in status_codes),
        }
        return last_response

    def _build_request(self, scenario: ChaosScenario, tamper: bool = False) -> dict[str, Any]:
        endpoint: Endpoint = scenario.endpoint
        url = f"{self._config.base_url}{endpoint.path}"

        kwargs: dict[str, Any] = {
            "method": endpoint.method.value,
            "url": url,
            "headers": {**self._config.headers},
        }

        if endpoint.method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
            body = self._build_default_body(endpoint)
            if tamper:
                body = self._apply_tampering(body, scenario.config)
            if body:
                kwargs["json"] = body

        params = {}
        for param in endpoint.parameters:
            if param.location == "query":
                params[param.name] = "test_value"
        if params:
            kwargs["params"] = params

        return kwargs

    def _apply_tampering(self, body: dict, tamper_config: dict) -> dict:
        body = copy.deepcopy(body)

        field_path = tamper_config.get("field_path", "")
        tamper_type = tamper_config.get("tamper_type", "remove")
        tamper_value = tamper_config.get("tamper_value")

        if not field_path:
            return body

        parts = field_path.split(".")
        current = body
        for part in parts[:-1]:
            if part in current and isinstance(current[part], dict):
                current = current[part]
            else:
                return body

        last_key = parts[-1]

        if tamper_type == "remove":
            current.pop(last_key, None)
        elif tamper_type == "replace":
            current[last_key] = tamper_value if tamper_value is not None else "TAMPERED"
        elif tamper_type == "overflow":
            current[last_key] = "A" * 10000
        elif tamper_type == "type_mismatch":
            original = current.get(last_key)
            if isinstance(original, str):
                current[last_key] = 12345
            elif isinstance(original, (int, float)):
                current[last_key] = "not_a_number"
            else:
                current[last_key] = {"nested": "unexpected"}
        elif tamper_type == "inject":
            current[last_key] = tamper_value if tamper_value is not None else True

        return body

    async def _send_with_retry(
        self,
        scenario: ChaosScenario,
        tamper: bool = False,
    ) -> ResponseData:
        request_kwargs = self._build_request(scenario, tamper=tamper)
        last_error: str | None = None
        max_attempts = 1 + self._config.max_retries

        for attempt in range(max_attempts):
            try:
                async with self._semaphore:
                    return await self._do_request(request_kwargs)
            except httpx.TimeoutException:
                raise
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError) as exc:
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    delay = self._calculate_backoff(attempt)
                    await asyncio.sleep(delay)
            except Exception as exc:
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    delay = self._calculate_backoff(attempt)
                    await asyncio.sleep(delay)

        raise httpx.ConnectError(last_error or "All retries exhausted")

    def _calculate_backoff(self, attempt: int) -> float:
        delay = min(
            self._exec_cfg.backoff_base * (2**attempt),
            self._exec_cfg.backoff_max,
        )
        jitter = delay * self._exec_cfg.jitter_factor * random.random()
        return delay + jitter

    async def _do_request(self, request_kwargs: dict[str, Any]) -> ResponseData:
        client = await self._get_client()

        start = time.monotonic()
        response = await client.request(**request_kwargs)
        elapsed = (time.monotonic() - start) * 1000

        return ResponseData(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=self._safe_json(response),
            elapsed_ms=round(elapsed, 2),
        )

    async def _execute_parallel(self, scenarios: list[ChaosScenario]) -> list[ScenarioResult]:
        tasks = [self._execute_single(s) for s in scenarios]
        return list(await asyncio.gather(*tasks))

    @staticmethod
    def _build_default_body(endpoint: Endpoint) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if endpoint.request_body and endpoint.request_body.fields:
            for field in endpoint.request_body.fields:
                if field.field_type == FieldType.STRING:
                    body[field.field_name] = "test_string"
                elif field.field_type in (FieldType.INTEGER,):
                    body[field.field_name] = 42
                elif field.field_type == FieldType.NUMBER:
                    body[field.field_name] = 3.14
                elif field.field_type == FieldType.BOOLEAN:
                    body[field.field_name] = False
                elif field.field_type == FieldType.ARRAY:
                    body[field.field_name] = []
                elif field.field_type == FieldType.OBJECT:
                    body[field.field_name] = {}
                else:
                    body[field.field_name] = None
        else:
            body = {"name": "test", "id": 1}
        return body

    @staticmethod
    def _detect_vulnerability(scenario: ChaosScenario, response: ResponseData) -> bool:
        if scenario.scenario_type == ChaosScenarioType.ERROR_STATUS:
            expected_status = scenario.config.get("status_code")
            if response.status_code == expected_status:
                return True

        if scenario.scenario_type == ChaosScenarioType.RATE_LIMIT:
            if isinstance(response.body, dict):
                return not response.body.get("rate_limited", False)

        if scenario.scenario_type == ChaosScenarioType.REQUEST_TAMPERING:
            if response.status_code and 200 <= response.status_code < 300:
                return True

        return False

    @staticmethod
    def _build_details(scenario: ChaosScenario, response: ResponseData) -> str:
        parts = [
            f"Type: {scenario.scenario_type.value}",
            f"Endpoint: {scenario.endpoint.method.value} {scenario.endpoint.path}",
        ]
        if response.status_code:
            parts.append(f"Status: {response.status_code}")
        if response.elapsed_ms:
            parts.append(f"Elapsed: {response.elapsed_ms:.1f}ms")
        if response.error:
            parts.append(f"Error: {response.error}")
        return " | ".join(parts)

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (ValueError, TypeError):
            return response.text
