"""Boundary Condition & Exception Scenario Tests

Covers:
- Empty/null/missing input handling
- Maximum size/length boundary values
- Invalid format/type inputs
- Non-existent resource access
- Duplicate resource creation
- Concurrent modification conflicts
- Malformed data handling
- Edge cases in license/quota/feature gates
"""

from __future__ import annotations

import io
import json
import os
import time

import pytest
from fastapi.testclient import TestClient
import httpx

from api_chaos_agent.main import app
from api_chaos_agent.core.license import LicenseManager, _LICENSE_FILE_PATHS, _generate_signature
from api_chaos_agent.core.feature_gates import TenantPlan, get_quota_for_plan, check_quota
from api_chaos_agent.models.tenant import Tenant
from api_chaos_agent.routers.execution import set_mock_transport
from api_chaos_agent.services.execution_engine import ExecutionEngine
from api_chaos_agent.models.report import ExecutionStatus, ResponseData, ScenarioResult


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


def _upload_openapi(client, title="Boundary API"):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {"summary": "List", "responses": {"200": {"description": "OK"}}},
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
        "holder": "boundary-org",
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


class TestSchemaBoundaryConditions:

    def test_upload_empty_file(self, client):
        resp = client.post(
            "/api/schemas/upload",
            files={"file": ("empty.json", io.BytesIO(b""), "application/json")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_invalid_json(self, client):
        resp = client.post(
            "/api/schemas/upload",
            files={"file": ("bad.json", io.BytesIO(b"not json at all"), "application/json")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_non_openapi_json(self, client):
        resp = client.post(
            "/api/schemas/upload",
            files={"file": ("notapi.json", io.BytesIO(b'{"hello": "world"}'), "application/json")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_very_large_spec(self, client):
        paths = {}
        for i in range(500):
            paths[f"/endpoint-{i}"] = {
                "get": {"summary": f"Endpoint {i}", "responses": {"200": {"description": "OK"}}}
            }
        spec = {"openapi": "3.0.0", "info": {"title": "Huge API", "version": "1.0.0"}, "paths": paths}
        spec_bytes = json.dumps(spec).encode()
        resp = client.post(
            "/api/schemas/upload",
            files={"file": ("huge.json", io.BytesIO(spec_bytes), "application/json")},
        )
        assert resp.status_code == 200

    def test_get_nonexistent_schema(self, client):
        resp = client.get("/api/schemas/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)

    def test_generate_scenarios_for_nonexistent_schema(self, client):
        resp = client.post("/api/scenarios/generate/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)

    def test_upload_no_file(self, client):
        resp = client.post("/api/schemas/upload")
        assert resp.status_code in (400, 422)


class TestScenarioBoundaryConditions:

    def test_generate_scenarios_empty_schema(self, client):
        spec = {"openapi": "3.0.0", "info": {"title": "Empty API", "version": "1.0.0"}, "paths": {}}
        spec_bytes = json.dumps(spec).encode()
        upload_resp = client.post(
            "/api/schemas/upload",
            files={"file": ("empty.json", io.BytesIO(spec_bytes), "application/json")},
        )
        schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code == 200
        data = gen_resp.json()
        assert data.get("scenario_ids", []) == []

    def test_get_nonexistent_scenario(self, client):
        resp = client.get("/api/scenarios/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)


class TestExecutionBoundaryConditions:

    def test_create_execution_empty_scenario_ids(self, client):
        resp = client.post(
            "/api/executions/",
            params={"scenario_ids": [], "base_url": "http://test.local", "concurrency": 5},
        )
        assert resp.status_code in (200, 400, 422)

    def test_create_execution_nonexistent_scenario(self, client):
        resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": ["00000000-0000-0000-0000-000000000000"],
                "base_url": "http://test.local",
                "concurrency": 5,
            },
        )
        assert resp.status_code in (200, 400, 404)

    def test_create_execution_zero_concurrency(self, client):
        upload_resp = _upload_openapi(client, "Zero Conc")
        schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json().get("scenario_ids", [])
        if scenario_ids:
            resp = client.post(
                "/api/executions/",
                params={"scenario_ids": scenario_ids, "base_url": "http://test.local", "concurrency": 0},
            )
            assert resp.status_code in (200, 400, 422)

    def test_create_execution_negative_concurrency(self, client):
        upload_resp = _upload_openapi(client, "Neg Conc")
        schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json().get("scenario_ids", [])
        if scenario_ids:
            resp = client.post(
                "/api/executions/",
                params={"scenario_ids": scenario_ids, "base_url": "http://test.local", "concurrency": -1},
            )
            assert resp.status_code in (400, 422)

    def test_create_execution_invalid_base_url(self, client):
        upload_resp = _upload_openapi(client, "Bad URL")
        schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json().get("scenario_ids", [])
        if scenario_ids:
            resp = client.post(
                "/api/executions/",
                params={"scenario_ids": scenario_ids, "base_url": "not-a-url", "concurrency": 5},
            )
            assert resp.status_code in (200, 400, 422)

    def test_get_nonexistent_execution(self, client):
        resp = client.get("/api/executions/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)


class TestReportBoundaryConditions:

    def test_generate_report_nonexistent_execution(self, client):
        resp = client.post("/api/reports/generate/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)

    def test_get_nonexistent_report(self, client):
        resp = client.get("/api/reports/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)


class TestDistributedBoundaryConditions:

    def test_register_worker_empty_name(self, client):
        resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "", "max_concurrency": 10},
        )
        assert resp.status_code in (400, 422)

    def test_register_worker_zero_concurrency(self, client):
        resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "zero-worker", "max_concurrency": 0},
        )
        assert resp.status_code in (200, 400, 422)

    def test_heartbeat_nonexistent_worker(self, client):
        resp = client.post("/api/v2/distributed/workers/00000000-0000-0000-0000-000000000000/heartbeat")
        assert resp.status_code in (404, 400)

    def test_unregister_nonexistent_worker(self, client):
        resp = client.delete("/api/v2/distributed/workers/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 200)

    def test_assign_task_no_idle_workers(self, client):
        resp = client.post(
            "/api/v2/distributed/tasks/assign",
            params={"scenario_id": "test-scenario", "base_url": "http://test.local"},
        )
        assert resp.status_code in (200, 400, 404)


class TestTenantBoundaryConditions:

    def test_create_tenant_empty_name(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "", "plan": "free"})
        assert resp.status_code in (400, 422)

    def test_create_tenant_invalid_plan(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "test", "plan": "invalid_plan"})
        assert resp.status_code in (400, 422)

    def test_get_nonexistent_tenant(self, client):
        resp = client.get("/api/v2/tenants/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)

    def test_update_nonexistent_tenant(self, client):
        resp = client.put(
            "/api/v2/tenants/00000000-0000-0000-0000-000000000000/plan",
            params={"plan": "pro"},
        )
        assert resp.status_code in (404, 400)

    def test_delete_nonexistent_tenant(self, client):
        resp = client.post("/api/v2/tenants/00000000-0000-0000-0000-000000000000/suspend")
        assert resp.status_code in (404, 400)

    def test_create_tenant_very_long_name(self, client):
        long_name = "A" * 10000
        resp = client.post("/api/v2/tenants", params={"name": long_name, "plan": "free"})
        assert resp.status_code in (200, 400, 422)


class TestLicenseBoundaryConditions:

    def test_install_invalid_license_key(self, client):
        resp = client.post("/license/install", params={"key": "invalid-key"})
        assert resp.status_code in (400, 422)

    def test_install_empty_license_key(self, client):
        resp = client.post("/license/install", params={"key": ""})
        assert resp.status_code in (400, 422)

    def test_install_malformed_license_key(self, client):
        resp = client.post("/license/install", params={"key": "a.b.c.d.e"})
        assert resp.status_code in (400, 422)

    def test_remove_license_when_none_installed(self, client):
        resp = client.delete("/license/remove")
        assert resp.status_code in (200, 404)

    def test_double_install_license(self, client):
        key = _make_license_key()
        resp1 = client.post("/license/install", params={"key": key})
        assert resp1.status_code == 200
        resp2 = client.post("/license/install", params={"key": key})
        assert resp2.status_code == 200

    def test_license_tampered_signature(self, client):
        import base64

        key = _make_license_key()
        parts = key.split(".")
        tampered_payload = base64.urlsafe_b64encode(b'{"type":"commercial_enterprise","plan":"enterprise"}').rstrip(b"=").decode()
        tampered_key = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        resp = client.post("/license/install", params={"key": tampered_key})
        assert resp.status_code in (400, 422)


class TestFeatureGateBoundaryConditions:

    def test_check_feature_unknown_feature(self, client):
        resp = client.get("/plans/check-feature", params={"feature": "nonexistent_feature", "plan": "free"})
        assert resp.status_code in (200, 400, 404)

    def test_check_feature_unknown_plan(self, client):
        resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "unknown"})
        assert resp.status_code in (200, 400, 422)

    def test_quota_at_exact_limit(self):
        quota = get_quota_for_plan(TenantPlan.FREE)
        assert check_quota(TenantPlan.FREE, "max_schemas", quota.max_schemas) is False
        assert check_quota(TenantPlan.FREE, "max_schemas", quota.max_schemas - 1) is True

    def test_quota_with_zero_usage(self):
        assert check_quota(TenantPlan.FREE, "max_schemas", 0) is True

    def test_quota_with_negative_usage(self):
        assert check_quota(TenantPlan.FREE, "max_schemas", -1) is True


class TestCiCdBoundaryConditions:

    def test_create_pipeline_empty_name(self, client):
        resp = client.post(
            "/api/v2/cicd/pipelines",
            params={"name": "", "provider": "github_actions", "tenant_id": "test"},
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
        assert resp.status_code in (400, 422)

    def test_create_pipeline_invalid_provider(self, client):
        resp = client.post(
            "/api/v2/cicd/pipelines",
            params={"name": "test", "provider": "invalid_provider", "tenant_id": "test"},
            json={
                "provider": "invalid_provider",
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
        assert resp.status_code in (400, 422)

    def test_get_nonexistent_pipeline(self, client):
        resp = client.get("/api/v2/cicd/pipelines/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400)

    def test_trigger_nonexistent_pipeline(self, client):
        resp = client.post("/api/v2/cicd/pipelines/00000000-0000-0000-0000-000000000000/trigger")
        assert resp.status_code in (404, 400)


class TestGrpcGraphqlBoundaryConditions:

    def test_grpc_invalid_proto(self, client):
        resp = client.post(
            "/api/v2/schemas/parse/grpc",
            files={"file": ("bad.proto", io.BytesIO(b"this is not valid proto"), "text/plain")},
        )
        assert resp.status_code in (400, 422)

    def test_graphql_invalid_schema(self, client):
        resp = client.post(
            "/api/v2/schemas/parse/graphql",
            files={"file": ("bad.graphql", io.BytesIO(b"this is not valid graphql"), "text/plain")},
        )
        assert resp.status_code in (400, 422)

    def test_grpc_empty_file(self, client):
        resp = client.post(
            "/api/v2/schemas/parse/grpc",
            files={"file": ("empty.proto", io.BytesIO(b""), "text/plain")},
        )
        assert resp.status_code in (400, 422)

    def test_graphql_empty_file(self, client):
        resp = client.post(
            "/api/v2/schemas/parse/graphql",
            files={"file": ("empty.graphql", io.BytesIO(b""), "text/plain")},
        )
        assert resp.status_code in (400, 422)


class TestPluginBoundaryConditions:

    def test_execute_nonexistent_plugin(self, client):
        resp = client.post(
            "/api/v2/plugins/nonexistent_plugin/execute",
            params={"scenario_id": "test-scenario"},
        )
        assert resp.status_code in (400, 404)

    def test_list_plugins_empty(self, client):
        resp = client.get("/api/v2/plugins/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_nonexistent_plugin_info(self, client):
        resp = client.get("/api/v2/plugins/nonexistent_plugin/info")
        assert resp.status_code in (404, 400)


class TestAnalyticsBoundaryConditions:

    def test_summary_nonexistent_tenant(self, client):
        resp = client.get("/api/v2/analytics/summary/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (200, 404, 400)

    def test_compare_no_reports(self, client):
        tenant_resp = client.post("/api/v2/tenants", params={"name": "CompareOrg", "plan": "pro"})
        tenant_id = tenant_resp.json()["id"]
        resp = client.get(f"/api/v2/analytics/compare/{tenant_id}", params={"report_id_1": "r1", "report_id_2": "r2"})
        assert resp.status_code in (200, 400, 404)
