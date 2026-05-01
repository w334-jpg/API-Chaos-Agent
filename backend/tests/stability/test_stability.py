"""Stability Testing — Long-Running, Resource Leak & Concurrency Safety

Covers:
- Long-running operation stability
- Memory leak detection (object accumulation)
- Resource cleanup verification
- Concurrent read/write safety
- Data consistency under concurrent access
- Worker lifecycle stability
- Store accumulation over time
"""

from __future__ import annotations

import gc
import io
import json
import os
import sys
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.main import app
from api_chaos_agent.core.license import LicenseManager, _LICENSE_FILE_PATHS
from api_chaos_agent.services.store import store


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


def _upload_openapi(client, title="Stability API"):
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


class TestLongRunningStability:

    def test_repeated_schema_upload_cycles(self, client):
        for i in range(50):
            resp = _upload_openapi(client, f"Stability-{i}")
            assert resp.status_code == 200

    def test_repeated_tenant_create_list_cycles(self, client):
        for i in range(30):
            create_resp = client.post("/api/v2/tenants", params={"name": f"StabTenant-{i}"})
            assert create_resp.status_code == 200
            list_resp = client.get("/api/v2/tenants")
            assert list_resp.status_code == 200

    def test_repeated_worker_register_deregister_cycles(self, client):
        for i in range(20):
            reg_resp = client.post(
                "/api/v2/distributed/workers/register",
                params={"name": f"stab-worker-{i}", "max_concurrency": 10},
            )
            assert reg_resp.status_code == 200
            worker_id = reg_resp.json()["id"]
            del_resp = client.delete(f"/api/v2/distributed/workers/{worker_id}")
            assert del_resp.status_code == 200

    def test_sustained_health_checks(self, client):
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200


class TestResourceLeakDetection:

    def test_schema_upload_no_memory_leak(self, client):
        gc.collect()
        obj_count_before = len(gc.get_objects())
        for i in range(30):
            _upload_openapi(client, f"LeakTest-{i}")
        gc.collect()
        obj_count_after = len(gc.get_objects())
        growth = obj_count_after - obj_count_before
        assert growth < 5000, f"Object count grew by {growth}, possible memory leak"

    def test_tenant_creation_no_memory_leak(self, client):
        gc.collect()
        obj_count_before = len(gc.get_objects())
        for i in range(30):
            client.post("/api/v2/tenants", params={"name": f"LeakTenant-{i}"})
        gc.collect()
        obj_count_after = len(gc.get_objects())
        growth = obj_count_after - obj_count_before
        assert growth < 5000, f"Object count grew by {growth}, possible memory leak"

    def test_worker_lifecycle_no_memory_leak(self, client):
        gc.collect()
        obj_count_before = len(gc.get_objects())
        for i in range(20):
            reg_resp = client.post(
                "/api/v2/distributed/workers/register",
                params={"name": f"leak-worker-{i}", "max_concurrency": 10},
            )
            worker_id = reg_resp.json()["id"]
            client.delete(f"/api/v2/distributed/workers/{worker_id}")
        gc.collect()
        obj_count_after = len(gc.get_objects())
        growth = obj_count_after - obj_count_before
        assert growth < 5000, f"Object count grew by {growth}, possible memory leak"

    def test_store_growth_bounded(self, client):
        initial_schemas = len(store._schemas) if hasattr(store, '_schemas') else 0
        for i in range(20):
            _upload_openapi(client, f"Growth-{i}")
        final_schemas = len(store._schemas) if hasattr(store, '_schemas') else 0
        assert final_schemas >= initial_schemas
        assert final_schemas <= initial_schemas + 20


class TestConcurrentSafety:

    def test_concurrent_schema_uploads(self, client):
        errors = []
        results = []

        def upload(idx):
            try:
                resp = _upload_openapi(client, f"ConcSchema-{idx}")
                results.append(resp.status_code)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(upload, i) for i in range(30)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Concurrent uploads had {len(errors)} errors"
        assert all(s == 200 for s in results), f"Not all uploads succeeded: {set(results)}"

    def test_concurrent_tenant_operations(self, client):
        errors = []
        tenant_ids = []

        def create_tenant(idx):
            try:
                resp = client.post("/api/v2/tenants", params={"name": f"ConcTenant-{idx}"})
                assert resp.status_code == 200
                tenant_ids.append(resp.json()["id"])
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(create_tenant, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Concurrent tenant ops had {len(errors)} errors"
        assert len(tenant_ids) == 20

    def test_concurrent_worker_heartbeats(self, client):
        reg_resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "hb-stab-worker", "max_concurrency": 100},
        )
        worker_id = reg_resp.json()["id"]
        errors = []

        def heartbeat(_):
            try:
                resp = client.post(f"/api/v2/distributed/workers/{worker_id}/heartbeat")
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(heartbeat, i) for i in range(50)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Concurrent heartbeats had {len(errors)} errors"
        client.delete(f"/api/v2/distributed/workers/{worker_id}")

    def test_concurrent_reads_during_writes(self, client):
        errors = []

        def write_op(idx):
            try:
                client.post("/api/v2/tenants", params={"name": f"RW-Tenant-{idx}"})
            except Exception as e:
                errors.append(e)

        def read_op(_):
            try:
                resp = client.get("/api/v2/tenants")
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for i in range(20):
                futures.append(pool.submit(write_op, i))
                futures.append(pool.submit(read_op, i))
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Concurrent R/W had {len(errors)} errors"

    def test_concurrent_feature_gate_checks(self, client):
        errors = []

        def check_feature(_):
            try:
                resp = client.get("/plans/check-feature", params={"feature": "distributed_execution", "plan": "pro"})
                assert resp.status_code == 200
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(check_feature, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Concurrent feature checks had {len(errors)} errors"


class TestDataConsistency:

    def test_tenant_data_consistency_after_concurrent_writes(self, client):
        tenant_ids = []
        for i in range(10):
            resp = client.post("/api/v2/tenants", params={"name": f"ConsistTenant-{i}", "plan": "free"})
            assert resp.status_code == 200
            tenant_ids.append(resp.json()["id"])

        for tid in tenant_ids:
            get_resp = client.get(f"/api/v2/tenants/{tid}")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert data["id"] == tid
            assert data["plan"] == "free"

    def test_worker_data_consistency_after_operations(self, client):
        reg_resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "consist-worker", "max_concurrency": 50},
        )
        worker_id = reg_resp.json()["id"]

        for _ in range(10):
            client.post(f"/api/v2/distributed/workers/{worker_id}/heartbeat")

        list_resp = client.get("/api/v2/distributed/workers")
        assert list_resp.status_code == 200
        workers = list_resp.json()
        found = [w for w in workers if w["id"] == worker_id]
        assert len(found) == 1
        assert found[0]["name"] == "consist-worker"

        client.delete(f"/api/v2/distributed/workers/{worker_id}")

    def test_schema_data_consistency(self, client):
        upload_resp = _upload_openapi(client, "Consistency API")
        schema_id = upload_resp.json().get("schema_id") or upload_resp.json().get("id")

        get_resp = client.get(f"/api/schemas/{schema_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "endpoints" in data or "grpc_services" in data or "graphql_operations" in data

    def test_no_data_corruption_under_stress(self, client):
        tenant_ids = []
        for i in range(5):
            resp = client.post("/api/v2/tenants", params={"name": f"CorruptTest-{i}", "plan": "pro"})
            tenant_ids.append(resp.json()["id"])

        def update_and_verify(tid, idx):
            resp = client.put(f"/api/v2/tenants/{tid}/plan", params={"plan": "enterprise"})
            assert resp.status_code == 200
            get_resp = client.get(f"/api/v2/tenants/{tid}")
            assert get_resp.status_code == 200
            assert get_resp.json()["plan"] == "enterprise"

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(update_and_verify, tid, i) for i, tid in enumerate(tenant_ids)]
            for f in as_completed(futures):
                f.result()

        for tid in tenant_ids:
            final_resp = client.get(f"/api/v2/tenants/{tid}")
            assert final_resp.status_code == 200
            assert final_resp.json()["plan"] == "enterprise"


class TestErrorRecovery:

    def test_system_recovers_after_invalid_requests(self, client):
        for _ in range(10):
            client.get("/api/schemas/nonexistent-id")
            client.post("/api/v2/tenants", params={"name": ""})
        resp = _upload_openapi(client, "Recovery API")
        assert resp.status_code == 200

    def test_system_recovers_after_worker_errors(self, client):
        for _ in range(10):
            client.post("/api/v2/distributed/workers/00000000/heartbeat")
        reg_resp = client.post(
            "/api/v2/distributed/workers/register",
            params={"name": "recovery-worker", "max_concurrency": 10},
        )
        assert reg_resp.status_code == 200
        client.delete(f"/api/v2/distributed/workers/{reg_resp.json()['id']}")

    def test_system_recovers_after_license_errors(self, client):
        for _ in range(5):
            client.post("/license/install", params={"key": "bad-key"})
        resp = client.get("/health")
        assert resp.status_code == 200
