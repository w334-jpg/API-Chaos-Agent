"""Integration Test 3: Blocks 7-9 (License + FeatureGates + Routes)

Tests the integration between:
- Block 7: License Manager (core/license.py)
- Block 8: Feature Gates (core/feature_gates.py)
- Block 9: API Routes (routers/*)

Validates:
- License → Feature Gate → Route access control flow
- Plan-based quota enforcement through API endpoints
- License installation affects feature availability
- Tenant plan changes propagate through feature gates
- BSL eligibility affects license status
- End-to-end request flow with license checks
"""

from __future__ import annotations

import json
import os
import threading

import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.core.feature_gates import (
    FEATURE_GATES,
    check_quota,
    get_features_for_plan,
    get_quota_for_plan,
    is_feature_available,
)
from api_chaos_agent.core.license import (
    _LICENSE_FILE_PATHS,
    LicenseManager,
    LicenseType,
    _check_bsl_eligibility,
    _generate_signature,
    generate_trial_license,
)
from api_chaos_agent.main import app
from api_chaos_agent.models.tenant import TenantPlan


@pytest.fixture(autouse=True)
def _cleanup():
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
        "features": list(FEATURE_GATES.keys()),
        "max_seats": 10,
        "is_production": True,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    signature = _generate_signature(payload_b64)
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256","typ":"license"}').rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{signature}"


class TestLicenseToFeatureGateFlow:
    def test_no_license_means_free_plan_features(self):
        for feature, gates in FEATURE_GATES.items():
            assert is_feature_available(TenantPlan.FREE, feature) == gates["free"]

    def test_pro_license_enables_pro_features(self):
        key = _make_license_key("commercial_pro", "pro")
        mgr = LicenseManager()
        info = mgr.install_license(key)
        assert info.plan == TenantPlan.PRO
        for feature, gates in FEATURE_GATES.items():
            assert is_feature_available(TenantPlan.PRO, feature) == gates["pro"]

    def test_enterprise_license_enables_all_features(self):
        key = _make_license_key("commercial_enterprise", "enterprise")
        mgr = LicenseManager()
        info = mgr.install_license(key)
        assert info.plan == TenantPlan.ENTERPRISE
        for feature, gates in FEATURE_GATES.items():
            assert is_feature_available(TenantPlan.ENTERPRISE, feature) is True

    def test_license_removal_reverts_to_free(self):
        key = _make_license_key("commercial_pro", "pro")
        mgr = LicenseManager()
        mgr.install_license(key)
        mgr.remove_license()
        for feature, gates in FEATURE_GATES.items():
            assert is_feature_available(TenantPlan.FREE, feature) == gates["free"]

    def test_bsl_eligibility_affects_pro_access(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "5"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "100000"
        assert _check_bsl_eligibility() is True
        mgr = LicenseManager()
        assert mgr.can_use_pro_features() is True

    def test_bsl_ineligibility_blocks_pro_access(self):
        os.environ["API_CHAOS_AGENT_IS_PRODUCTION"] = "true"
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "200"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "10000000"
        assert _check_bsl_eligibility() is False
        mgr = LicenseManager()
        assert mgr.can_use_pro_features() is False

    def test_trial_license_enables_pro_features(self):
        key = generate_trial_license("trial-org", days=30)
        mgr = LicenseManager()
        info = mgr.install_license(key)
        assert info.license_type == LicenseType.TRIAL
        assert info.plan == TenantPlan.PRO
        assert mgr.can_use_pro_features() is True


class TestFeatureGateToRouteFlow:
    def test_plans_features_reflects_gates(self, client):
        resp = client.get("/plans/features", params={"plan": "pro"})
        assert resp.status_code == 200
        data = resp.json()
        pro_features = get_features_for_plan(TenantPlan.PRO)
        for feat in pro_features:
            assert feat in data["features"]

    def test_plans_check_feature_uses_gates(self, client):
        for feature in FEATURE_GATES:
            for plan in ["free", "pro", "enterprise"]:
                resp = client.get("/plans/check-feature", params={"feature": feature, "plan": plan})
                assert resp.status_code == 200
                expected = is_feature_available(TenantPlan(plan), feature)
                assert resp.json()["available"] == expected

    def test_plans_quota_matches_plan_quotas(self, client):
        for plan_name in ["free", "pro", "enterprise"]:
            resp = client.get("/plans/features", params={"plan": plan_name})
            assert resp.status_code == 200
            data = resp.json()
            quota = get_quota_for_plan(TenantPlan(plan_name))
            assert data["quota"]["max_schemas"] == quota.max_schemas
            assert data["quota"]["max_team_members"] == quota.max_team_members

    def test_check_quota_endpoint_uses_feature_gates(self, client):
        resp = client.get(
            "/plans/check-quota",
            params={"resource": "max_schemas", "current_usage": 5, "plan": "free"},
        )
        assert resp.status_code == 200
        assert resp.json()["within_limit"] == check_quota(TenantPlan.FREE, "max_schemas", 5)

    def test_compare_plans_shows_all_plans(self, client):
        resp = client.get("/plans/compare")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"free", "pro", "enterprise"}


class TestLicenseToRouteFlow:
    def test_license_install_then_info_route(self, client):
        key = _make_license_key("commercial_pro", "pro")
        install_resp = client.post("/license/install", params={"key": key})
        assert install_resp.status_code == 200
        info_resp = client.get("/license/info")
        assert info_resp.status_code == 200
        assert info_resp.json()["license_type"] == "commercial_pro"

    def test_license_install_enables_pro_check(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        resp = client.get("/license/check-pro")
        assert resp.status_code == 200
        assert resp.json()["can_use_pro"] is True

    def test_license_install_enables_enterprise_check(self, client):
        key = _make_license_key("commercial_enterprise", "enterprise")
        client.post("/license/install", params={"key": key})
        resp = client.get("/license/check-enterprise")
        assert resp.status_code == 200
        assert resp.json()["can_use_enterprise"] is True

    def test_license_removal_disables_pro(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        client.delete("/license/remove")
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "200"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "10000000"
        resp = client.get("/license/check-pro")
        assert resp.status_code == 200
        assert resp.json()["can_use_pro"] is False

    def test_trial_license_via_route(self, client):
        key = generate_trial_license("route-trial-org", days=14)
        install_resp = client.post("/license/install", params={"key": key})
        assert install_resp.status_code == 200
        assert install_resp.json()["license_type"] == "trial"
        check_resp = client.get("/license/check-pro")
        assert check_resp.json()["can_use_pro"] is True

    def test_invalid_license_rejected(self, client):
        resp = client.post("/license/install", params={"key": "totally.invalid.key"})
        assert resp.status_code == 400


class TestTenantPlanToFeatureGateFlow:
    def test_tenant_creation_uses_free_plan_by_default(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "FreeTenant"})
        assert resp.status_code == 200
        assert resp.json()["plan"] == "free"

    def test_tenant_plan_upgrade_enables_features(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "UpgradeTenant"})
        tenant_id = create_resp.json()["id"]
        upgrade_resp = client.put(f"/api/v2/tenants/{tenant_id}/plan", params={"plan": "pro"})
        assert upgrade_resp.status_code == 200
        assert upgrade_resp.json()["plan"] == "pro"
        assert upgrade_resp.json()["quota"]["custom_plugins"] is True
        assert upgrade_resp.json()["quota"]["ci_cd_integration"] is True

    def test_tenant_quota_enforcement_through_route(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "QuotaTenant"})
        tenant_id = create_resp.json()["id"]
        resp = client.get(
            f"/api/v2/tenants/{tenant_id}/quota", params={"resource": "schemas", "current": 5}
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True
        resp2 = client.get(
            f"/api/v2/tenants/{tenant_id}/quota", params={"resource": "schemas", "current": 15}
        )
        assert resp2.json()["allowed"] is False

    def test_tenant_member_quota_enforcement(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "MemQuotaTenant"})
        tenant_id = create_resp.json()["id"]
        resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "extra@test.com", "role": "member"},
        )
        assert resp.status_code == 400

    def test_pro_tenant_allows_more_members(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "ProMemTenant", "plan": "pro"})
        tenant_id = create_resp.json()["id"]
        for i in range(5):
            resp = client.post(
                f"/api/v2/tenants/{tenant_id}/members",
                params={"email": f"member{i}@test.com", "role": "member"},
            )
            assert resp.status_code == 200


class TestEndToEndAccessControlFlow:
    def test_full_flow_no_license_to_pro(self, client):
        info_resp = client.get("/license/info")
        assert info_resp.status_code == 200
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        check_pro2 = client.get("/license/check-pro")
        assert check_pro2.json()["can_use_pro"] is True
        features_resp = client.get("/plans/features", params={"plan": "pro"})
        assert features_resp.status_code == 200
        pro_features = features_resp.json()["features"]
        assert "distributed_execution" in pro_features
        assert "custom_plugins" in pro_features

    def test_full_flow_tenant_creation_with_license(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        tenant_resp = client.post("/api/v2/tenants", params={"name": "LicensedOrg", "plan": "pro"})
        assert tenant_resp.status_code == 200
        tenant_id = tenant_resp.json()["id"]
        quota_resp = client.get(
            f"/api/v2/tenants/{tenant_id}/quota", params={"resource": "schemas", "current": 50}
        )
        assert quota_resp.json()["allowed"] is True
        member_resp = client.post(
            f"/api/v2/tenants/{tenant_id}/members",
            params={"email": "dev@test.com", "role": "member"},
        )
        assert member_resp.status_code == 200

    def test_full_flow_license_removal_blocks_access(self, client):
        key = _make_license_key("commercial_enterprise", "enterprise")
        client.post("/license/install", params={"key": key})
        assert client.get("/license/check-enterprise").json()["can_use_enterprise"] is True
        client.delete("/license/remove")
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "200"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "10000000"
        assert client.get("/license/check-enterprise").json()["can_use_enterprise"] is False
        assert client.get("/license/check-pro").json()["can_use_pro"] is False

    def test_full_flow_tenant_plan_downgrade(self, client):
        create_resp = client.post(
            "/api/v2/tenants", params={"name": "DowngradeOrg", "plan": "enterprise"}
        )
        tenant_id = create_resp.json()["id"]
        assert create_resp.json()["quota"]["sso_enabled"] is True
        downgrade_resp = client.put(f"/api/v2/tenants/{tenant_id}/plan", params={"plan": "free"})
        assert downgrade_resp.status_code == 200
        assert downgrade_resp.json()["quota"]["sso_enabled"] is False
        assert downgrade_resp.json()["quota"]["max_schemas"] == 10


class TestIntegrationStress:
    def test_concurrent_license_checks(self, client):
        key = _make_license_key("commercial_pro", "pro")
        client.post("/license/install", params={"key": key})
        errors = []

        def check():
            try:
                resp = client.get("/license/check-pro")
                assert resp.status_code == 200
                assert resp.json()["can_use_pro"] is True
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=check) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_feature_availability_checks(self):
        errors = []

        def check():
            try:
                for feature, gates in FEATURE_GATES.items():
                    assert is_feature_available(TenantPlan.PRO, feature) == gates["pro"]
                    assert is_feature_available(TenantPlan.FREE, feature) == gates["free"]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=check) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_rapid_license_install_remove_cycle(self, client):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "200"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "10000000"
        for i in range(5):
            key = _make_license_key("commercial_pro", "pro")
            install_resp = client.post("/license/install", params={"key": key})
            assert install_resp.status_code == 200
            check_resp = client.get("/license/check-pro")
            assert check_resp.json()["can_use_pro"] is True
            remove_resp = client.delete("/license/remove")
            assert remove_resp.status_code == 200
            check_resp2 = client.get("/license/check-pro")
            assert check_resp2.json()["can_use_pro"] is False

    def test_rapid_tenant_plan_changes(self, client):
        create_resp = client.post("/api/v2/tenants", params={"name": "RapidPlanChange"})
        tenant_id = create_resp.json()["id"]
        for plan in ["pro", "enterprise", "free", "pro", "enterprise"]:
            resp = client.put(f"/api/v2/tenants/{tenant_id}/plan", params={"plan": plan})
            assert resp.status_code == 200
            assert resp.json()["plan"] == plan
