"""Performance Testing & Bottleneck Analysis

Comprehensive performance benchmarks covering:
- API endpoint response time under load
- Throughput measurement for critical paths
- Concurrent operation stress testing
- Memory and resource utilization profiling
- Bottleneck identification and analysis
"""

from __future__ import annotations

import io
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.core.license import (
    _LICENSE_FILE_PATHS,
    LicenseManager,
    _generate_signature,
)
from api_chaos_agent.main import app
from api_chaos_agent.models.report import ExecutionStatus, ResponseData, ScenarioResult
from api_chaos_agent.services.execution_engine import ExecutionEngine


def _mock_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"mocked": True})


MOCK_TRANSPORT = httpx.MockTransport(_mock_handler)


_original_execute = ExecutionEngine.execute


async def _mock_execute(self, scenarios):
    results = []
    for s in scenarios:
        sr = ScenarioResult(
            scenario_id=s.id,
            scenario_name=s.name,
            scenario_type=s.scenario_type.value,
            severity=s.severity,
        )
        sr.status = ExecutionStatus.COMPLETED
        sr.response = ResponseData(status_code=200, body={"mocked": True}, elapsed_ms=1.0)
        sr.vulnerability_found = False
        sr.details = "Mocked execution"
        results.append(sr)
    from api_chaos_agent.models.report import TestResult

    tr = TestResult(total_scenarios=len(scenarios), config=self._config)
    tr.results = results
    tr.completed_scenarios = len(results)
    tr.failed_scenarios = 0
    tr.completed_at = tr.started_at.__class__.now()
    return tr


BENCHMARK_ITERATIONS = 50
CONCURRENT_THREADS = 20
RESPONSE_TIME_SLO_MS = 500.0
THROUGHPUT_SLO_RPS = 10.0


@pytest.fixture(autouse=True)
def _cleanup():
    LicenseManager._instance = None
    LicenseManager._license_info = None
    LicenseManager._last_check = 0.0
    ExecutionEngine.execute = _mock_execute
    for key in list(os.environ.keys()):
        if key.startswith("API_CHAOS_AGENT_"):
            del os.environ[key]
    for path in _LICENSE_FILE_PATHS:
        if path.exists():
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    yield
    ExecutionEngine.execute = _original_execute
    LicenseManager._instance = None
    LicenseManager._license_info = None
    LicenseManager._last_check = 0.0


@pytest.fixture
def client():
    return TestClient(app)


def _upload_openapi(client, title="Perf API"):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {"summary": "List users", "responses": {"200": {"description": "OK"}}},
            },
        },
    }
    spec_bytes = json.dumps(spec).encode()
    return client.post(
        "/api/schemas/upload",
        files={"file": ("openapi.json", io.BytesIO(spec_bytes), "application/json")},
    )


def _make_license_key(license_type="commercial_pro", plan="pro"):
    import base64
    from datetime import datetime, timedelta

    now = datetime.now()
    expires = now + timedelta(days=365)
    payload = {
        "type": license_type,
        "holder": "perf-org",
        "plan": plan,
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "features": ["distributed_execution", "custom_plugins"],
        "max_seats": 10,
        "is_production": True,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    signature = _generate_signature(payload_b64)
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256","typ":"license"}').rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{signature}"


class _PerfResult:
    def __init__(self, name: str, times: list[float]):
        self.name = name
        self.times = times
        self.mean_ms = statistics.mean(times) * 1000
        self.p50_ms = statistics.median(times) * 1000
        self.p95_ms = (
            sorted(times)[int(len(times) * 0.95)] * 1000 if len(times) >= 20 else self.p50_ms
        )
        self.p99_ms = (
            sorted(times)[int(len(times) * 0.99)] * 1000 if len(times) >= 100 else self.p95_ms
        )
        self.min_ms = min(times) * 1000
        self.max_ms = max(times) * 1000
        self.stdev_ms = statistics.stdev(times) * 1000 if len(times) > 1 else 0.0
        self.throughput_rps = len(times) / sum(times) if sum(times) > 0 else 0.0

    def __str__(self):
        return (
            f"[{self.name}] "
            f"mean={self.mean_ms:.1f}ms p50={self.p50_ms:.1f}ms p95={self.p95_ms:.1f}ms "
            f"min={self.min_ms:.1f}ms max={self.max_ms:.1f}ms "
            f"throughput={self.throughput_rps:.1f}rps"
        )


def _benchmark(client, name, fn, iterations=BENCHMARK_ITERATIONS):
    times = []
    for _ in range(iterations):
        start = time.monotonic()
        fn(client)
        times.append(time.monotonic() - start)
    result = _PerfResult(name, times)
    return result


class TestSchemaPerformance:
    def test_schema_upload_response_time(self, client):
        result = _benchmark(
            client, "schema_upload", lambda c: _upload_openapi(c, f"Perf-{time.monotonic_ns()}")
        )
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Schema upload p95={result.p95_ms:.1f}ms exceeds SLO"
        )
        assert result.throughput_rps >= THROUGHPUT_SLO_RPS, (
            f"Schema upload throughput={result.throughput_rps:.1f}rps below SLO"
        )

    def test_schema_list_response_time(self, client):
        for i in range(5):
            _upload_openapi(client, f"ListPerf-{i}")
        result = _benchmark(client, "schema_list", lambda c: c.get("/api/schemas/"))
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Schema list p95={result.p95_ms:.1f}ms exceeds SLO"
        )

    def test_schema_upload_concurrent_throughput(self, client):
        start = time.monotonic()
        errors = []

        def upload(idx):
            try:
                _upload_openapi(client, f"Concurrent-{idx}")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as pool:
            futures = [pool.submit(upload, i) for i in range(CONCURRENT_THREADS)]
            for f in as_completed(futures):
                f.result()

        elapsed = time.monotonic() - start
        throughput = CONCURRENT_THREADS / elapsed
        assert len(errors) == 0, f"Concurrent uploads had {len(errors)} errors"
        assert throughput >= 5.0, f"Concurrent throughput={throughput:.1f}rps below minimum"


class TestScenarioPerformance:
    def test_scenario_generation_response_time(self, client):
        upload_resp = _upload_openapi(client, "ScenarioPerf")
        schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")
        result = _benchmark(
            client,
            "scenario_generate",
            lambda c: c.post(f"/api/scenarios/generate/{schema_id}"),
        )
        assert result.p95_ms < RESPONSE_TIME_SLO_MS * 2, (
            f"Scenario gen p95={result.p95_ms:.1f}ms exceeds SLO"
        )

    def test_scenario_list_response_time(self, client):
        result = _benchmark(client, "scenario_list", lambda c: c.get("/api/scenarios/"))
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Scenario list p95={result.p95_ms:.1f}ms exceeds SLO"
        )


class TestExecutionPerformance:
    def test_execution_list_response_time(self, client):
        result = _benchmark(client, "execution_list", lambda c: c.get("/api/executions/"))
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Execution list p95={result.p95_ms:.1f}ms exceeds SLO"
        )


class TestReportPerformance:
    def test_report_list_response_time(self, client):
        result = _benchmark(client, "report_list", lambda c: c.get("/api/reports/"))
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Report list p95={result.p95_ms:.1f}ms exceeds SLO"
        )


class TestDistributedPerformance:
    def test_worker_register_throughput(self, client):
        worker_ids = []

        def register(idx):
            resp = client.post(
                "/api/v2/distributed/workers/register",
                params={"name": f"perf-worker-{idx}", "max_concurrency": 100},
            )
            assert resp.status_code == 200
            worker_ids.append(resp.json()["id"])

        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as pool:
            futures = [pool.submit(register, i) for i in range(CONCURRENT_THREADS)]
            for f in as_completed(futures):
                f.result()
        elapsed = time.monotonic() - start
        throughput = CONCURRENT_THREADS / elapsed
        assert throughput >= 10.0, f"Worker register throughput={throughput:.1f}rps below minimum"

        for wid in worker_ids:
            client.delete(f"/api/v2/distributed/workers/{wid}")

    def test_worker_heartbeat_response_time(self, client):
        reg_resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "hb-perf-worker", "max_concurrency": 100},
        )
        worker_id = reg_resp.json()["id"]
        result = _benchmark(
            client,
            "worker_heartbeat",
            lambda c: c.post(f"/api/v2/distributed/workers/{worker_id}/heartbeat"),
        )
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Heartbeat p95={result.p95_ms:.1f}ms exceeds SLO"
        )
        client.delete(f"/api/v2/distributed/workers/{worker_id}")


class TestTenantPerformance:
    def test_tenant_crud_response_time(self, client):
        create_times = []
        for i in range(20):
            start = time.monotonic()
            resp = client.post(
                "/api/v2/tenants", params={"name": f"PerfTenant-{i}", "plan": "free"}
            )
            create_times.append(time.monotonic() - start)
            assert resp.status_code == 200

        result = _PerfResult("tenant_create", create_times)
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Tenant create p95={result.p95_ms:.1f}ms exceeds SLO"
        )

    def test_tenant_list_response_time(self, client):
        for i in range(10):
            client.post("/api/v2/tenants", params={"name": f"ListPerfTenant-{i}"})
        result = _benchmark(client, "tenant_list", lambda c: c.get("/api/v2/tenants"))
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Tenant list p95={result.p95_ms:.1f}ms exceeds SLO"
        )


class TestLicensePerformance:
    def test_license_check_response_time(self, client):
        key = _make_license_key()
        client.post("/license/install", params={"key": key})
        result = _benchmark(
            client,
            "license_check_pro",
            lambda c: c.get("/license/check-pro"),
        )
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"License check p95={result.p95_ms:.1f}ms exceeds SLO"
        )

    def test_feature_gate_check_throughput(self, client):
        start = time.monotonic()
        for _ in range(500):
            resp = client.get(
                "/plans/check-feature", params={"feature": "distributed_execution", "plan": "pro"}
            )
            assert resp.status_code == 200
        elapsed = time.monotonic() - start
        throughput = 500 / elapsed
        assert throughput >= 50.0, f"Feature gate throughput={throughput:.1f}rps below minimum"


class TestCiCdPerformance:
    def test_pipeline_crud_response_time(self, client):
        create_times = []
        for i in range(10):
            start = time.monotonic()
            resp = client.post(
                "/api/v2/cicd/pipelines",
                params={
                    "name": f"PerfPipeline-{i}",
                    "provider": "github_actions",
                    "tenant_id": "perf-tenant",
                },
                json={
                    "provider": "github_actions",
                    "project_url": "https://github.com/test/repo",
                    "branch": "main",
                    "api_spec_path": "openapi.yaml",
                    "scenario_types": ["latency"],
                    "fail_on_severity": "high",
                    "base_url": "http://test.local",
                    "concurrency": 10,
                    "timeout_seconds": 300.0,
                },
            )
            create_times.append(time.monotonic() - start)
            assert resp.status_code == 200

        result = _PerfResult("pipeline_create", create_times)
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Pipeline create p95={result.p95_ms:.1f}ms exceeds SLO"
        )


class TestAnalyticsPerformance:
    def test_analytics_summary_response_time(self, client):
        tenant_resp = client.post(
            "/api/v2/tenants", params={"name": "AnalyticsPerfOrg", "plan": "pro"}
        )
        tenant_id = tenant_resp.json()["id"]
        result = _benchmark(
            client,
            "analytics_summary",
            lambda c: c.get(f"/api/v2/analytics/summary/{tenant_id}"),
        )
        assert result.p95_ms < RESPONSE_TIME_SLO_MS, (
            f"Analytics summary p95={result.p95_ms:.1f}ms exceeds SLO"
        )


class TestHealthPerformance:
    def test_health_endpoint_throughput(self, client):
        start = time.monotonic()
        for _ in range(500):
            resp = client.get("/health")
            assert resp.status_code == 200
        elapsed = time.monotonic() - start
        throughput = 500 / elapsed
        assert throughput >= 2.0, f"Health endpoint throughput={throughput:.1f}rps below minimum"


class TestBottleneckAnalysis:
    def test_full_pipeline_latency_breakdown(self, client):
        upload_times = []
        gen_times = []
        exec_times = []

        for i in range(10):
            start = time.monotonic()
            upload_resp = _upload_openapi(client, f"Pipeline-{i}")
            upload_times.append(time.monotonic() - start)

            schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")

            start = time.monotonic()
            gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
            gen_times.append(time.monotonic() - start)

            scenario_ids = gen_resp.json().get("scenario_ids", [])
            if scenario_ids:
                start = time.monotonic()
                client.post(
                    "/api/executions/",
                    params={
                        "scenario_ids": scenario_ids,
                        "base_url": "http://test.local",
                        "concurrency": 5,
                    },
                )
                exec_times.append(time.monotonic() - start)

        upload_result = _PerfResult("pipeline_upload", upload_times)
        gen_result = _PerfResult("pipeline_generate", gen_times)
        exec_result = _PerfResult("pipeline_execute", exec_times) if exec_times else None

        assert upload_result.p95_ms < RESPONSE_TIME_SLO_MS, f"Upload bottleneck: {upload_result}"
        assert gen_result.p95_ms < RESPONSE_TIME_SLO_MS * 2, f"Generate bottleneck: {gen_result}"
        if exec_result:
            assert exec_result.p50_ms < RESPONSE_TIME_SLO_MS * 10, (
                f"Execute bottleneck: {exec_result}"
            )

    def test_mixed_workload_sustained(self, client):
        key = _make_license_key()
        client.post("/license/install", params={"key": key})

        ops = []
        errors = []

        def schema_op(idx):
            try:
                start = time.monotonic()
                _upload_openapi(client, f"Mixed-{idx}")
                ops.append(time.monotonic() - start)
            except Exception as e:
                errors.append(e)

        def tenant_op(idx):
            try:
                start = time.monotonic()
                client.post("/api/v2/tenants", params={"name": f"MixedTenant-{idx}"})
                ops.append(time.monotonic() - start)
            except Exception as e:
                errors.append(e)

        def feature_op(_):
            try:
                start = time.monotonic()
                client.get(
                    "/plans/check-feature",
                    params={"feature": "distributed_execution", "plan": "pro"},
                )
                ops.append(time.monotonic() - start)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for i in range(30):
                futures.append(pool.submit(schema_op, i))
                futures.append(pool.submit(tenant_op, i))
                futures.append(pool.submit(feature_op, i))
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Mixed workload had {len(errors)} errors"
        assert len(ops) >= 80, f"Only {len(ops)} ops completed"
        if ops:
            p95 = sorted(ops)[int(len(ops) * 0.95)] * 1000
            assert p95 < RESPONSE_TIME_SLO_MS * 3, f"Mixed workload p95={p95:.1f}ms exceeds SLO"
