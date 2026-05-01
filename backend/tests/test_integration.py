"""End-to-end integration tests for the full API Chaos Agent workflow."""

from __future__ import annotations

import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.main import app
from api_chaos_agent.routers.execution import set_mock_transport
from api_chaos_agent.services.store import store

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PETSTORE_JSON = FIXTURES_DIR / "petstore_openapi.json"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if "pets" in request.url.path and request.method == "GET":
        return httpx.Response(
            status_code=200, json=[{"id": 1, "name": "Fido", "status": "available"}]
        )
    if "pets" in request.url.path and request.method == "POST":
        return httpx.Response(status_code=201, json={"id": 2, "name": "NewPet"})
    if "pets" in request.url.path and request.method == "DELETE":
        return httpx.Response(status_code=204)
    return httpx.Response(status_code=200, json={"status": "ok"})


MOCK_TRANSPORT = httpx.MockTransport(_mock_handler)


@pytest.fixture(autouse=True)
def clean_store():
    store.clear_sync()
    set_mock_transport(MOCK_TRANSPORT)
    yield
    store.clear_sync()
    set_mock_transport(None)


@pytest.fixture
def client():
    return TestClient(app)


def _upload_petstore(client):
    data = PETSTORE_JSON.read_bytes()
    return client.post(
        "/api/schemas/upload",
        files={"file": ("petstore.json", data, "application/json")},
    )


class TestFullWorkflow:
    def test_complete_chaos_testing_workflow(self, client):
        upload_resp = _upload_petstore(client)
        assert upload_resp.status_code in (200, 201)
        upload_data = upload_resp.json()
        schema_id = upload_data["schema_id"]
        assert upload_data["title"] == "Petstore API"
        assert upload_data["endpoints"] >= 2

        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["scenarios_generated"] > 0
        scenario_ids = gen_data["scenario_ids"]

        exec_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids,
                "base_url": "https://petstore.example.com/v1",
                "timeout_seconds": 5.0,
                "concurrency": 2,
                "serial": True,
            },
        )
        assert exec_resp.status_code == 200
        exec_data = exec_resp.json()
        execution_id = exec_data["execution_id"]
        assert exec_data["total_scenarios"] == len(scenario_ids)

        exec_detail = client.get(f"/api/executions/{execution_id}")
        assert exec_detail.status_code == 200
        detail = exec_detail.json()
        assert detail["total_scenarios"] == len(scenario_ids)
        assert detail["completed_scenarios"] + detail["failed_scenarios"] == len(scenario_ids)

        report_resp = client.post(f"/api/reports/generate/{execution_id}")
        assert report_resp.status_code == 200
        report_data = report_resp.json()
        report_id = report_data["report_id"]
        assert report_data["summary"]["total_scenarios"] == len(scenario_ids)

        get_report_resp = client.get(f"/api/reports/{report_id}")
        assert get_report_resp.status_code == 200
        full_report = get_report_resp.json()
        assert full_report["id"] == report_id
        assert len(full_report["findings"]) > 0

        assert "summary" in full_report

    def test_schema_list_after_upload(self, client):
        _upload_petstore(client)
        list_resp = client.get("/api/schemas/")
        assert list_resp.status_code == 200
        schemas = list_resp.json()["schemas"]
        assert len(schemas) >= 1
        assert schemas[0]["title"] == "Petstore API"

    def test_scenario_list_after_generation(self, client):
        upload_resp = _upload_petstore(client)
        schema_id = upload_resp.json()["schema_id"]

        client.post(f"/api/scenarios/generate/{schema_id}")
        list_resp = client.get("/api/scenarios/")
        assert list_resp.status_code == 200
        scenarios = list_resp.json()["scenarios"]
        assert len(scenarios) > 0

    def test_health_check_in_workflow(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_execution_list_after_run(self, client):
        upload_resp = _upload_petstore(client)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json()["scenario_ids"]

        client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids[:2],
                "base_url": "https://petstore.example.com/v1",
                "serial": True,
            },
        )
        list_resp = client.get("/api/executions/")
        assert list_resp.status_code == 200
        executions = list_resp.json()["executions"]
        assert len(executions) >= 1

    def test_report_list_after_generation(self, client):
        upload_resp = _upload_petstore(client)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json()["scenario_ids"]

        exec_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids[:2],
                "base_url": "https://petstore.example.com/v1",
                "serial": True,
            },
        )
        execution_id = exec_resp.json()["execution_id"]

        client.post(f"/api/reports/generate/{execution_id}")
        list_resp = client.get("/api/reports/")
        assert list_resp.status_code == 200
        reports = list_resp.json()["reports"]
        assert len(reports) >= 1


class TestWorkflowErrorRecovery:
    def test_upload_invalid_then_valid_file(self, client):
        bad_resp = client.post(
            "/api/schemas/upload",
            files={"file": ("bad.txt", b"not a spec", "text/plain")},
        )
        assert bad_resp.status_code == 400

        good_resp = _upload_petstore(client)
        assert good_resp.status_code in (200, 201)

    def test_execution_with_nonexistent_scenario_then_valid(self, client):
        bad_resp = client.post(
            "/api/executions/",
            params={"scenario_ids": ["nonexistent"], "base_url": "https://example.com"},
        )
        assert bad_resp.status_code == 404

        upload_resp = _upload_petstore(client)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json()["scenario_ids"]

        good_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids[:2],
                "base_url": "https://petstore.example.com/v1",
                "timeout_seconds": 5.0,
                "serial": True,
            },
        )
        assert good_resp.status_code == 200

    def test_report_for_nonexistent_execution_then_valid(self, client):
        bad_resp = client.post("/api/reports/generate/nonexistent")
        assert bad_resp.status_code == 404

        upload_resp = _upload_petstore(client)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json()["scenario_ids"]

        exec_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids[:2],
                "base_url": "https://petstore.example.com/v1",
                "serial": True,
            },
        )
        execution_id = exec_resp.json()["execution_id"]

        good_resp = client.post(f"/api/reports/generate/{execution_id}")
        assert good_resp.status_code == 200

    def test_html_report_format(self, client):
        upload_resp = _upload_petstore(client)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        scenario_ids = gen_resp.json()["scenario_ids"]

        exec_resp = client.post(
            "/api/executions/",
            params={
                "scenario_ids": scenario_ids[:2],
                "base_url": "https://petstore.example.com/v1",
                "serial": True,
            },
        )
        execution_id = exec_resp.json()["execution_id"]

        report_resp = client.post(f"/api/reports/generate/{execution_id}?format=html")
        assert report_resp.status_code == 200
        report_data = report_resp.json()
        assert report_data["format"] == "html"
        assert "html" in report_data
        assert "<html" in report_data["html"]
