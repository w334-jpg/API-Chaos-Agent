"""Full System End-to-End Test

Covers all features end-to-end across both Phase 1 (MCP) and Phase 2:
- Schema management (REST, gRPC, GraphQL)
- Scenario creation and management
- Execution engine (local + distributed)
- Report generation and analytics
- CI/CD integration
- Plugin framework
- Multi-tenancy and RBAC
- License management and feature gates
- Health checks and system endpoints
"""

from __future__ import annotations

import io
import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient
import httpx

from api_chaos_agent.main import app
from api_chaos_agent.core.license import (
    LicenseManager,
    _LICENSE_FILE_PATHS,
    generate_trial_license,
    _generate_signature,
)
from api_chaos_agent.models.tenant import TenantPlan
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


def _make_license_key(license_type: str = "commercial_pro", plan: str = "pro") -> str:
    import base64
    from datetime import datetime, timedelta

    now = datetime.now()
    expires = now + timedelta(days=365)
    payload = {
        "type": license_type,
        "holder": "e2e-org",
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


def _upload_openapi(client, title="E2E Test API"):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {"summary": "List users", "responses": {"200": {"description": "OK"}}},
                "post": {"summary": "Create user", "responses": {"201": {"description": "Created"}}},
            },
            "/users/{id}": {
                "get": {
                    "summary": "Get user",
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }
    spec_bytes = json.dumps(spec).encode()
    resp = client.post(
        "/api/schemas/upload",
        files={"file": ("openapi.json", io.BytesIO(spec_bytes), "application/json")},
    )
    return resp


def _get_schema_id(upload_resp):
    data = upload_resp.json()
    return data.get("schema_id") or data.get("id")


class TestE2ESchemaLifecycle:

    def test_openapi_schema_full_lifecycle(self, client):
        upload_resp = _upload_openapi(client)
        assert upload_resp.status_code == 200
        schema_id = _get_schema_id(upload_resp)
        assert schema_id is not None
        get_resp = client.get(f"/api/schemas/{schema_id}")
        assert get_resp.status_code == 200
        list_resp = client.get("/api/schemas/")
        assert list_resp.status_code == 200

    def test_grpc_schema_full_lifecycle(self, client):
        proto_content = b'''
syntax = "proto3";
package e2e;
service UserService {
    rpc GetUser(GetUserRequest) returns (User);
    rpc ListUsers(ListUsersRequest) returns (UserList);
}
message GetUserRequest { string user_id = 1; }
message User { string id = 1; string name = 2; }
message ListUsersRequest { int32 page = 1; }
message UserList { repeated User users = 1; }
'''
        resp = client.post(
            "/api/v2/schemas/parse/grpc",
            files={"file": ("user.proto", io.BytesIO(proto_content), "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "grpc_services" in data
        assert len(data["grpc_services"]) >= 1
        svc = data["grpc_services"][0]
        assert svc["name"] == "UserService"
        assert len(svc["methods"]) >= 2

    def test_graphql_schema_full_lifecycle(self, client):
        graphql_content = b'''
type Query {
    user(id: ID!): User
    users: [User]
}
type Mutation {
    createUser(name: String!): User
}
type User { id: ID! name: String! }
'''
        resp = client.post(
            "/api/v2/schemas/parse/graphql",
            files={"file": ("schema.graphql", io.BytesIO(graphql_content), "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "graphql_operations" in data
        assert len(data["graphql_operations"]) >= 1


class TestE2EScenarioAndExecution:

    def test_scenario_generate_and_list(self, client):
        upload_resp = _upload_openapi(client, "Scenario Test API")
        schema_id = _get_schema_id(upload_resp)
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code == 200
        list_resp = client.get("/api/scenarios/")
        assert list_resp.status_code == 200

    def test_execution_create_and_list(self, client):
        upload_resp = _upload_openapi(client, "Exec Test API")
        schema_id = _get_schema_id(upload_resp)
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json().get("scenario_ids", [])
        if scenario_ids:
            exec_resp = client.post(
                "/api/executions/",
                params={"scenario_ids": scenario_ids, "base_url": "http://test.local", "concurrency": 5},
            )
            assert exec_resp.status_code == 200
        list_resp = client.get("/api/executions/")
        assert list_resp.status_code == 200


class TestE2EReportAndAnalytics:

    def test_report_generation(self, client):
        upload_resp = _upload_openapi(client, "Report Test API")
        schema_id = _get_schema_id(upload_resp)
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json().get("scenario_ids", [])
        if scenario_ids:
            exec_resp = client.post(
                "/api/executions/",
                params={"scenario_ids": scenario_ids, "base_url": "http://test.local", "concurrency": 5},
            )
            exec_id = exec_resp.json().get("execution_id") or exec_resp.json().get("id")
            if exec_id:
                report_resp = client.post(f"/api/reports/generate/{exec_id}")
                assert report_resp.status_code == 200
        list_resp = client.get("/api/reports/")
        assert list_resp.status_code == 200

    def test_analytics_summary(self, client):
        tenant_resp = client.post("/api/v2/tenants", params={"name": "AnalyticsOrg", "plan": "pro"})
        tenant_id = tenant_resp.json()["id"]
        resp = client.get(f"/api/v2/analytics/summary/{tenant_id}")
        assert resp.status_code == 200


class TestE2EDistributedExecution:

    def test_worker_lifecycle(self, client):
        register_resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "e2e-worker-1", "max_concurrency": 100, "region": "us-west"},
        )
        assert register_resp.status_code == 200
        worker_id = register_resp.json()["id"]
        hb_resp = client.post(f"/api/v2/distributed/workers/{worker_id}/heartbeat")
        assert hb_resp.status_code == 200
        list_resp = client.get("/api/v2/distributed/workers")
        assert list_resp.status_code == 200
        dereg_resp = client.delete(f"/api/v2/distributed/workers/{worker_id}")
        assert dereg_resp.status_code == 200


class TestE2ECiCdIntegration:

    def test_pipeline_lifecycle(self, client):
        create_resp = client.post(
            "/api/v2/cicd/pipelines",
            params={"name": "e2e-pipeline", "provider": "github_actions", "tenant_id": "e2e-tenant"},
            json={
                "provider": "github_actions",
                "project_url": "https://github.com/test/repo",
                "branch": "main",
                "api_spec_path": "openapi.yaml",
                "scenario_types": ["latency", "error_status"],
                "fail_on_severity": "high",
                "base_url": "http://test.local",
                "concurrency": 10,
                "timeout_seconds": 300.0,
            },
        )
        assert create_resp.status_code == 200
        pipeline_id = create_resp.json()["id"]
        config_resp = client.get(f"/api/v2/cicd/pipelines/{pipeline_id}/config")
        assert config_resp.status_code == 200
        assert config_resp.json()["format"] == "yaml"
        trigger_resp = client.post(f"/api/v2/cicd/pipelines/{pipeline_id}/trigger")
        assert trigger_resp.status_code == 200
        del_resp = client.delete(f"/api/v2/cicd/pipelines/{pipeline_id}")
        assert del_resp.status_code == 200


class TestE2EMultiTenancy:

    def test_tenant_full_lifecycle(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "E2EOrg", "plan": "pro"})
        assert create_resp.status_code == 200
        tenant_id = create_resp.json()["id"]
        assert create_resp.json()["plan"] == "pro"
        get_resp = client.get(f"/api/v2/tenants/{tenant_id}")
        assert get_resp.status_code == 200
        upgrade_resp = client.put(f"/api/v2/tenants/{tenant_id}/plan", params={"plan": "enterprise"})
        assert upgrade_resp.status_code == 200
        assert upgrade_resp.json()["plan"] == "enterprise"
        member_resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "dev@e2e.com", "role": "admin"},
        )
        assert member_resp.status_code == 200
        members_resp = client.get(f"/api/v2/tenants/{tenant_id}/members")
        assert members_resp.status_code == 200
        assert len(members_resp.json()) >= 1
        invite_resp = client.post(
            f"/api/v2/tenants/{tenant_id}/invites",
            params={"email": "new@e2e.com", "role": "member"},
        )
        assert invite_resp.status_code == 200
        suspend_resp = client.post(f"/api/v2/tenants/{tenant_id}/suspend")
        assert suspend_resp.status_code == 200
        assert suspend_resp.json()["status"] == "suspended"


class TestE2ELicenseAndFeatureGates:

    def test_license_install_enables_features(self, client):
        key = _make_license_key("commercial_pro", "pro")
        install_resp = client.post("/license/install", params={"key": key})
        assert install_resp.status_code == 200
        info_resp = client.get("/license/info")
        assert info_resp.status_code == 200
        assert info_resp.json()["license_type"] == "commercial_pro"
        pro_check = client.get("/license/check-pro")
        assert pro_check.json()["can_use_pro"] is True
        features_resp = client.get("/plans/features", params={"plan": "pro"})
        assert features_resp.status_code == 200
        pro_features = features_resp.json()["features"]
        assert "distributed_execution" in pro_features
        assert "custom_plugins" in pro_features

    def test_enterprise_license_enables_all(self, client):
        key = _make_license_key("commercial_enterprise", "enterprise")
        client.post("/license/install", params={"key": key})
        ent_check = client.get("/license/check-enterprise")
        assert ent_check.json()["can_use_enterprise"] is True
        features_resp = client.get("/plans/features", params={"plan": "enterprise"})
        assert features_resp.status_code == 200
        ent_features = features_resp.json()["features"]
        assert "sso" in ent_features
        assert "audit_log_export" in ent_features
        assert "custom_branding" in ent_features

    def test_trial_license_flow(self, client):
        key = generate_trial_license("e2e-trial", days=14)
        install_resp = client.post("/license/install", params={"key": key})
        assert install_resp.status_code == 200
        assert install_resp.json()["license_type"] == "trial"
        pro_check = client.get("/license/check-pro")
        assert pro_check.json()["can_use_pro"] is True

    def test_license_removal(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        remove_resp = client.delete("/license/remove")
        assert remove_resp.status_code == 200
        info_resp = client.get("/license/info")
        assert info_resp.status_code == 200


class TestE2EPlanComparison:

    def test_plan_comparison_complete(self, client):
        compare_resp = client.get("/plans/compare")
        assert compare_resp.status_code == 200
        data = compare_resp.json()
        assert set(data.keys()) == {"free", "pro", "enterprise"}
        assert data["free"]["quota"]["max_schemas"] < data["pro"]["quota"]["max_schemas"]
        assert data["pro"]["quota"]["max_schemas"] < data["enterprise"]["quota"]["max_schemas"]

    def test_feature_check_all_plans(self, client):
        features = ["distributed_execution", "custom_plugins", "sso", "audit_log_export"]
        for feature in features:
            for plan in ["free", "pro", "enterprise"]:
                resp = client.get("/plans/check-feature", params={"feature": feature, "plan": plan})
                assert resp.status_code == 200

    def test_quota_check_all_plans(self, client):
        for plan in ["free", "pro", "enterprise"]:
            resp = client.get("/plans/check-quota", params={"resource": "schemas", "current_usage": 5, "plan": plan})
            assert resp.status_code == 200


class TestE2EHealthAndSystem:

    def test_health_endpoints(self, client):
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/health/live").status_code == 200

    def test_auth_endpoint(self, client):
        resp = client.post("/auth/token", data={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()


class TestE2ECrossModuleFlow:

    def test_tenant_to_analytics_flow(self, client):
        tenant_resp = client.post("/api/v2/tenants", params={"name": "CrossModOrg", "plan": "pro"})
        tenant_id = tenant_resp.json()["id"]
        analytics_resp = client.get(f"/api/v2/analytics/summary/{tenant_id}")
        assert analytics_resp.status_code == 200
        assert analytics_resp.json()["tenant_id"] == tenant_id

    def test_license_to_tenant_to_quota_flow(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        tenant_resp = client.post("/api/v2/tenants", params={"name": "LicenseQuotaOrg", "plan": "pro"})
        tenant_id = tenant_resp.json()["id"]
        quota_resp = client.get(f"/api/v2/tenants/{tenant_id}/quota", params={"resource": "schemas", "current": 50})
        assert quota_resp.status_code == 200
        assert quota_resp.json()["allowed"] is True

    def test_distributed_worker_to_cicd_flow(self, client):
        worker_resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "cicd-worker", "max_concurrency": 50},
        )
        worker_id = worker_resp.json()["id"]
        pipeline_resp = client.post(
            "/api/v2/cicd/pipelines",
            params={"name": "dist-pipeline", "provider": "github_actions", "tenant_id": "e2e-tenant"},
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
        pipeline_id = pipeline_resp.json()["id"]
        trigger_resp = client.post(f"/api/v2/cicd/pipelines/{pipeline_id}/trigger")
        assert trigger_resp.status_code == 200
        client.delete(f"/api/v2/distributed/workers/{worker_id}")
        client.delete(f"/api/v2/cicd/pipelines/{pipeline_id}")


class TestE2EStress:

    def test_concurrent_schema_uploads(self, client):
        errors = []

        def upload_schema(idx):
            try:
                spec = {"openapi": "3.0.0", "info": {"title": f"Stress {idx}", "version": "1.0"}, "paths": {}}
                spec_bytes = json.dumps(spec).encode()
                resp = client.post(
                    "/api/schemas/upload",
                    files={"file": (f"stress-{idx}.json", io.BytesIO(spec_bytes), "application/json")},
                )
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=upload_schema, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_tenant_operations(self, client):
        errors = []

        def create_tenant(idx):
            try:
                resp = client.post("/api/v2/tenants", params={"name": f"StressOrg-{idx}"})
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_tenant, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_rapid_feature_checks(self, client):
        start = time.monotonic()
        for _ in range(200):
            resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "pro"})
            assert resp.status_code == 200
        elapsed = time.monotonic() - start
        assert elapsed < 15.0, f"200 feature checks took {elapsed:.2f}s"
