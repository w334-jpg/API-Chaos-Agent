"""Block 9: API路由层 Phase2 — TDD增强测试

Covers all Phase 2 router endpoints:
- License router (/license/*)
- Plans router (/plans/*)
- Tenants router (/api/v2/tenants/*)
- Plugins router (/api/v2/plugins/*)
- CI/CD router (/api/v2/cicd/*)
- Distributed router (/api/v2/distributed/*)
- Analytics router (/api/v2/analytics/*)
- Schemas V2 router (/api/v2/schemas/*)
"""

from __future__ import annotations

import io
import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.main import app
from api_chaos_agent.core.license import (
    LicenseInfo,
    LicenseManager,
    LicenseStatus,
    LicenseType,
    _LICENSE_FILE_PATHS,
    generate_trial_license,
    _generate_signature,
)
from api_chaos_agent.models.tenant import TenantPlan


@pytest.fixture(autouse=True)
def _cleanup_license():
    LicenseManager._instance = None
    LicenseManager._license_info = None
    LicenseManager._last_check = 0.0
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
    LicenseManager._instance = None
    LicenseManager._license_info = None
    LicenseManager._last_check = 0.0
    for key in list(os.environ.keys()):
        if key.startswith("API_CHAOS_AGENT_"):
            del os.environ[key]


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
        "holder": "test-org",
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


class TestLicenseRouter:

    def test_get_license_info_default(self, client):
        resp = client.get("/license/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["license_type"] in ("bsl", "trial", "commercial_pro", "commercial_enterprise")
        assert data["status"] in ("valid", "expired", "invalid", "missing", "bsl_non_production")

    def test_install_valid_license(self, client):
        key = _make_license_key("commercial_pro", "pro")
        resp = client.post("/license/install", params={"key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert data["license_type"] == "commercial_pro"
        assert data["plan"] == "pro"

    def test_install_trial_license(self, client):
        key = generate_trial_license("test-org", days=30)
        resp = client.post("/license/install", params={"key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert data["license_type"] == "trial"

    def test_install_invalid_license(self, client):
        resp = client.post("/license/install", params={"key": "invalid.key.here"})
        assert resp.status_code == 400

    def test_remove_license(self, client):
        key = _make_license_key()
        client.post("/license/install", params={"key": key})
        resp = client.delete("/license/remove")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

    def test_check_pro_access_without_license(self, client):
        resp = client.get("/license/check-pro")
        assert resp.status_code == 200
        data = resp.json()
        assert "can_use_pro" in data

    def test_check_enterprise_access_without_license(self, client):
        resp = client.get("/license/check-enterprise")
        assert resp.status_code == 200
        data = resp.json()
        assert "can_use_enterprise" in data

    def test_check_pro_access_with_pro_license(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        resp = client.get("/license/check-pro")
        assert resp.status_code == 200
        assert resp.json()["can_use_pro"] is True

    def test_check_enterprise_access_with_pro_license(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        resp = client.get("/license/check-enterprise")
        assert resp.status_code == 200
        assert resp.json()["can_use_enterprise"] is False

    def test_check_enterprise_access_with_enterprise_license(self, client):
        key = _make_license_key("commercial_enterprise", "enterprise")
        client.post("/license/install", params={"key": key})
        resp = client.get("/license/check-enterprise")
        assert resp.status_code == 200
        assert resp.json()["can_use_enterprise"] is True

    def test_install_license_then_remove_then_info(self, client):
        key = _make_license_key()
        client.post("/license/install", params={"key": key})
        client.delete("/license/remove")
        resp = client.get("/license/info")
        assert resp.status_code == 200


class TestPlansRouter:

    def test_list_features_default_free(self, client):
        resp = client.get("/plans/features")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "free"
        assert "features" in data
        assert "quota" in data

    def test_list_features_pro(self, client):
        resp = client.get("/plans/features", params={"plan": "pro"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro"

    def test_list_features_enterprise(self, client):
        resp = client.get("/plans/features", params={"plan": "enterprise"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "enterprise"

    def test_list_features_invalid_plan(self, client):
        resp = client.get("/plans/features", params={"plan": "premium"})
        assert resp.status_code == 400

    def test_compare_plans(self, client):
        resp = client.get("/plans/compare")
        assert resp.status_code == 200
        data = resp.json()
        assert "free" in data
        assert "pro" in data
        assert "enterprise" in data
        for plan_data in data.values():
            assert "features" in plan_data
            assert "quota" in plan_data

    def test_check_feature_available(self, client):
        resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "pro"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True

    def test_check_feature_not_available(self, client):
        resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "free"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False

    def test_check_feature_invalid_plan(self, client):
        resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "invalid"})
        assert resp.status_code == 400

    def test_check_quota_within_limit(self, client):
        resp = client.get("/plans/check-quota", params={"resource": "max_schemas", "current_usage": 5, "plan": "free"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["within_limit"] is True

    def test_check_quota_exceeded(self, client):
        resp = client.get("/plans/check-quota", params={"resource": "max_schemas", "current_usage": 15, "plan": "free"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["within_limit"] is False

    def test_check_quota_invalid_plan(self, client):
        resp = client.get("/plans/check-quota", params={"resource": "max_schemas", "current_usage": 5, "plan": "gold"})
        assert resp.status_code == 400


class TestTenantsRouter:

    def test_create_tenant(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "TestOrg"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "TestOrg"
        assert data["plan"] == "free"
        assert "id" in data

    def test_create_tenant_with_plan(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "ProOrg", "plan": "pro"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro"

    def test_list_tenants(self, client):
        client.post("/api/v2/tenants", params={"name": "Org1"})
        resp = client.get("/api/v2/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_tenant(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "GetOrg"})
        tenant_id = create_resp.json()["id"]
        resp = client.get(f"/api/v2/tenants/{tenant_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetOrg"

    def test_get_tenant_not_found(self, client):
        resp = client.get("/api/v2/tenants/nonexistent-id")
        assert resp.status_code == 404

    def test_update_tenant_plan(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "UpgradeOrg"})
        tenant_id = create_resp.json()["id"]
        resp = client.put(f"/api/v2/tenants/{tenant_id}/plan", params={"plan": "pro"})
        assert resp.status_code == 200
        assert resp.json()["plan"] == "pro"

    def test_update_tenant_plan_not_found(self, client):
        resp = client.put("/api/v2/tenants/nonexistent-id/plan", params={"plan": "pro"})
        assert resp.status_code == 404

    def test_suspend_tenant(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "SuspendOrg"})
        tenant_id = create_resp.json()["id"]
        resp = client.post(f"/api/v2/tenants/{tenant_id}/suspend")
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

    def test_suspend_tenant_not_found(self, client):
        resp = client.post("/api/v2/tenants/nonexistent-id/suspend")
        assert resp.status_code == 404

    def test_check_tenant_quota(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "QuotaOrg"})
        tenant_id = create_resp.json()["id"]
        resp = client.get(f"/api/v2/tenants/{tenant_id}/quota", params={"resource": "max_schemas", "current": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed" in data

    def test_add_member(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "MemberOrg", "plan": "pro"})
        tenant_id = create_resp.json()["id"]
        resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "user@test.com", "role": "member", "display_name": "Test User"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_email"] == "user@test.com"

    def test_add_member_free_plan_quota_exceeded(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "FreeMemOrg"})
        tenant_id = create_resp.json()["id"]
        resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "user@test.com", "role": "member"},
        )
        assert resp.status_code == 400

    def test_list_members(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "ListMemOrg", "plan": "pro"})
        tenant_id = create_resp.json()["id"]
        client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "user1@test.com", "role": "member"},
        )
        resp = client.get(f"/api/v2/tenants/{tenant_id}/members")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_remove_member(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "RemMemOrg", "plan": "pro"})
        tenant_id = create_resp.json()["id"]
        member_resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "remove@test.com", "role": "member"},
        )
        member_id = member_resp.json()["id"]
        resp = client.delete(f"/api/v2/tenants/{tenant_id}/members/{member_id}")
        assert resp.status_code == 200

    def test_update_member_role(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "RoleOrg", "plan": "pro"})
        tenant_id = create_resp.json()["id"]
        member_resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "role@test.com", "role": "member"},
        )
        member_id = member_resp.json()["id"]
        resp = client.put(
            f"/api/v2/tenants/{tenant_id}/members/{member_id}/role",
            params={"role": "admin"},
        )
        assert resp.status_code == 200

    def test_create_invite(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "InviteOrg"})
        tenant_id = create_resp.json()["id"]
        resp = client.post(
            f"/api/v2/tenants/{tenant_id}/invites",
            params={"email": "invited@test.com", "role": "member"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "invited@test.com"

    def test_list_invites(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "ListInvOrg"})
        tenant_id = create_resp.json()["id"]
        client.post(
            f"/api/v2/tenants/{tenant_id}/invites",
            params={"email": "inv1@test.com", "role": "member"},
        )
        resp = client.get(f"/api/v2/tenants/{tenant_id}/invites")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_accept_invite(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "AcceptOrg", "plan": "pro"})
        tenant_id = create_resp.json()["id"]
        invite_resp = client.post(
            f"/api/v2/tenants/{tenant_id}/invites",
            params={"email": "accept@test.com", "role": "member"},
        )
        invite_id = invite_resp.json()["id"]
        resp = client.post(f"/api/v2/tenants/{tenant_id}/invites/{invite_id}/accept")
        assert resp.status_code == 200
        assert resp.json()["user_email"] == "accept@test.com"


class TestPluginsRouter:

    def test_list_plugins_empty(self, client):
        resp = client.get("/api/v2/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_plugin_not_found(self, client):
        resp = client.get("/api/v2/plugins/nonexistent-plugin")
        assert resp.status_code == 404

    def test_enable_plugin_not_found(self, client):
        resp = client.post("/api/v2/plugins/nonexistent-plugin/enable")
        assert resp.status_code == 404

    def test_disable_plugin_not_found(self, client):
        resp = client.post("/api/v2/plugins/nonexistent-plugin/disable")
        assert resp.status_code == 404

    def test_execute_plugin_not_found(self, client):
        resp = client.post(
            "/api/v2/plugins/nonexistent-plugin/execute",
            params={"scenario_id": "test-scenario"},
        )
        assert resp.status_code in (400, 404, 500)

    def test_load_from_nonexistent_directory(self, client):
        resp = client.post("/api/v2/plugins/load/directory", params={"directory": "/nonexistent/path"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["loaded"] == 0

    def test_load_from_invalid_entrypoint(self, client):
        resp = client.post("/api/v2/plugins/load/entrypoint", params={"module_path": "nonexistent.module:Plugin"})
        assert resp.status_code == 400


class TestCicdRouter:

    def _create_pipeline(self, client, name="test-pipeline", provider="github_actions"):
        return client.post(
            "/api/v2/cicd/pipelines",
            params={
                "name": name,
                "provider": provider,
                "tenant_id": "test-tenant",
            },
            json={
                "provider": provider,
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

    def test_create_pipeline(self, client):
        resp = self._create_pipeline(client)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-pipeline"
        assert "id" in data

    def test_list_pipelines(self, client):
        self._create_pipeline(client)
        resp = client.get("/api/v2/cicd/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_pipeline(self, client):
        create_resp = self._create_pipeline(client)
        pipeline_id = create_resp.json()["id"]
        resp = client.get(f"/api/v2/cicd/pipelines/{pipeline_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-pipeline"

    def test_get_pipeline_not_found(self, client):
        resp = client.get("/api/v2/cicd/pipelines/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_pipeline(self, client):
        create_resp = self._create_pipeline(client)
        pipeline_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v2/cicd/pipelines/{pipeline_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_pipeline_not_found(self, client):
        resp = client.delete("/api/v2/cicd/pipelines/nonexistent-id")
        assert resp.status_code == 404

    def test_generate_pipeline_config(self, client):
        create_resp = self._create_pipeline(client)
        pipeline_id = create_resp.json()["id"]
        resp = client.get(f"/api/v2/cicd/pipelines/{pipeline_id}/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert data["format"] == "yaml"

    def test_generate_pipeline_config_not_found(self, client):
        resp = client.get("/api/v2/cicd/pipelines/nonexistent-id/config")
        assert resp.status_code == 404

    def test_trigger_pipeline(self, client):
        create_resp = self._create_pipeline(client)
        pipeline_id = create_resp.json()["id"]
        resp = client.post(f"/api/v2/cicd/pipelines/{pipeline_id}/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_id"] == pipeline_id

    def test_trigger_pipeline_not_found(self, client):
        resp = client.post("/api/v2/cicd/pipelines/nonexistent-id/trigger")
        assert resp.status_code == 400

    def test_list_pipeline_runs(self, client):
        create_resp = self._create_pipeline(client)
        pipeline_id = create_resp.json()["id"]
        resp = client.get(f"/api/v2/cicd/pipelines/{pipeline_id}/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_gitlab_pipeline(self, client):
        resp = self._create_pipeline(client, name="gitlab-pipe", provider="gitlab_ci")
        assert resp.status_code == 200
        assert resp.json()["name"] == "gitlab-pipe"


class TestDistributedRouter:

    def test_register_worker(self, client):
        resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "worker-1", "max_concurrency": 50, "region": "us-east"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "worker-1"
        assert "id" in data

    def test_list_workers(self, client):
        client.post("/api/v2/distributed/workers/register", params={"name": "w1"})
        resp = client.get("/api/v2/distributed/workers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_deregister_worker(self, client):
        create_resp = client.post("/api/v2/distributed/workers/register", params={"name": "w2"})
        worker_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v2/distributed/workers/{worker_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deregistered"

    def test_deregister_worker_not_found(self, client):
        resp = client.delete("/api/v2/distributed/workers/nonexistent-id")
        assert resp.status_code == 404

    def test_worker_heartbeat(self, client):
        create_resp = client.post("/api/v2/distributed/workers/register", params={"name": "hb-worker"})
        worker_id = create_resp.json()["id"]
        resp = client.post(f"/api/v2/distributed/workers/{worker_id}/heartbeat")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_worker_heartbeat_not_found(self, client):
        resp = client.post("/api/v2/distributed/workers/nonexistent-id/heartbeat")
        assert resp.status_code == 404

    def test_get_execution_plan_not_found(self, client):
        resp = client.get("/api/v2/distributed/plans/nonexistent-id")
        assert resp.status_code == 404


class TestAnalyticsRouter:

    def test_get_analytics_summary(self, client):
        resp = client.get("/api/v2/analytics/summary/test-tenant")
        assert resp.status_code == 200
        data = resp.json()
        assert "tenant_id" in data
        assert "total_executions" in data

    def test_get_analytics_summary_with_period(self, client):
        resp = client.get("/api/v2/analytics/summary/test-tenant", params={"period": "monthly"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "monthly"

    def test_compare_reports_not_found(self, client):
        resp = client.get(
            "/api/v2/analytics/compare",
            params={"baseline_report_id": "nonexistent1", "comparison_report_id": "nonexistent2"},
        )
        assert resp.status_code == 404


class TestSchemasV2Router:

    def test_parse_grpc_schema(self, client):
        proto_content = b'''
syntax = "proto3";

package test;

service TestService {
    rpc GetUser(GetUserRequest) returns (User);
    rpc ListUsers(ListUsersRequest) returns (UserList);
}

message GetUserRequest {
    string user_id = 1;
}

message User {
    string id = 1;
    string name = 2;
    string email = 3;
}

message ListUsersRequest {
    int32 page = 1;
    int32 page_size = 2;
}

message UserList {
    repeated User users = 1;
    int32 total = 2;
}
'''
        resp = client.post(
            "/api/v2/schemas/parse",
            files={"file": ("test.proto", io.BytesIO(proto_content), "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "endpoints" in data

    def test_parse_graphql_schema(self, client):
        graphql_content = b'''
type Query {
    user(id: ID!): User
    users: [User]
}

type Mutation {
    createUser(input: CreateUserInput!): User
    updateUser(id: ID!, input: UpdateUserInput!): User
}

type User {
    id: ID!
    name: String!
    email: String!
}

input CreateUserInput {
    name: String!
    email: String!
}

input UpdateUserInput {
    name: String
    email: String
}
'''
        resp = client.post(
            "/api/v2/schemas/parse",
            files={"file": ("schema.graphql", io.BytesIO(graphql_content), "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "endpoints" in data

    def test_parse_openapi_rejected(self, client):
        openapi_content = json.dumps({"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0"}}).encode()
        resp = client.post(
            "/api/v2/schemas/parse",
            files={"file": ("openapi.json", io.BytesIO(openapi_content), "application/json")},
        )
        assert resp.status_code == 400

    def test_parse_grpc_direct(self, client):
        proto_content = b'syntax = "proto3"; service Svc { rpc M(Req) returns (Res); } message Req {} message Res {}'
        resp = client.post(
            "/api/v2/schemas/parse/grpc",
            files={"file": ("test.proto", io.BytesIO(proto_content), "text/plain")},
        )
        assert resp.status_code == 200

    def test_parse_graphql_direct(self, client):
        graphql_content = b'type Query { hello: String }'
        resp = client.post(
            "/api/v2/schemas/parse/graphql",
            files={"file": ("schema.graphql", io.BytesIO(graphql_content), "text/plain")},
        )
        assert resp.status_code == 200

    def test_parse_invalid_grpc(self, client):
        resp = client.post(
            "/api/v2/schemas/parse/grpc",
            files={"file": ("bad.proto", io.BytesIO(b"not valid proto"), "text/plain")},
        )
        assert resp.status_code in (200, 400, 422)

    def test_parse_invalid_graphql(self, client):
        resp = client.post(
            "/api/v2/schemas/parse/graphql",
            files={"file": ("bad.graphql", io.BytesIO(b"not valid graphql {}{}{}"), "text/plain")},
        )
        assert resp.status_code in (200, 400, 422)


class TestPhase2HealthAndAuth:

    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_readiness_check(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200

    def test_liveness_check(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_auth_token_disabled(self, client):
        resp = client.post("/auth/token", params={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data


class TestRouterStress:

    def test_concurrent_tenant_creation(self, client):
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

    def test_concurrent_worker_registration(self, client):
        errors = []

        def register_worker(idx):
            try:
                resp = client.post(
                    "/api/v2/distributed/workers/register",
                    params={"name": f"stress-worker-{idx}", "max_concurrency": 10},
                )
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_rapid_feature_checks(self, client):
        start = time.monotonic()
        for _ in range(100):
            resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "pro"})
            assert resp.status_code == 200
        elapsed = time.monotonic() - start
        assert elapsed < 10.0, f"100 feature checks took {elapsed:.2f}s"

    def test_rapid_quota_checks(self, client):
        start = time.monotonic()
        for _ in range(100):
            resp = client.get("/plans/check-quota", params={"resource": "max_schemas", "current_usage": 5, "plan": "free"})
            assert resp.status_code == 200
        elapsed = time.monotonic() - start
        assert elapsed < 10.0, f"100 quota checks took {elapsed:.2f}s"
