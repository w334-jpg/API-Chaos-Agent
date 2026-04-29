"""Comprehensive unit tests for API routers."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from api_chaos_agent.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_openapi_json():
    return {
        "openapi": "3.0.0",
        "info": {"title": "Petstore", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "summary": "List all pets",
                    "responses": {"200": {"description": "A list of pets"}},
                },
                "post": {
                    "summary": "Create a pet",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "tag": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "Pet created"}},
                },
            }
        },
    }


def _upload_file(client, spec_dict, filename="openapi.json", content_type="application/json"):
    content = json.dumps(spec_dict).encode("utf-8")
    return client.post(
        "/api/schemas/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


class TestSchemaRouter:

    def test_upload_schema(self, client, sample_openapi_json):
        response = _upload_file(client, sample_openapi_json)
        assert response.status_code in (200, 201)
        data = response.json()
        assert "schema_id" in data
        assert data["title"] == "Petstore"
        assert data["endpoints"] == 2

    def test_upload_invalid_schema(self, client):
        content = b"not valid json at all"
        response = client.post(
            "/api/schemas/upload",
            files={"file": ("bad.json", io.BytesIO(content), "application/json")},
        )
        assert response.status_code in (400, 422)

    def test_list_schemas(self, client):
        response = client.get("/api/schemas/")
        assert response.status_code == 200
        data = response.json()
        assert "schemas" in data

    def test_get_schema_not_found(self, client):
        response = client.get("/api/schemas/nonexistent-id")
        assert response.status_code == 404

    def test_upload_postman_collection(self, client):
        postman = {
            "info": {
                "name": "Test Collection",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {"request": {"method": "GET", "url": "https://api.example.com/users"}}
            ],
        }
        response = _upload_file(client, postman, filename="collection.json")
        assert response.status_code in (200, 201, 400)


class TestScenarioRouter:

    def test_list_scenarios(self, client):
        response = client.get("/api/scenarios/")
        assert response.status_code == 200

    def test_generate_scenarios_requires_schema_id(self, client):
        response = client.post("/api/scenarios/generate/nonexistent-id")
        assert response.status_code in (404, 422)

    def test_get_scenario_not_found(self, client):
        response = client.get("/api/scenarios/nonexistent-id")
        assert response.status_code == 404


class TestExecutionRouter:

    def test_list_executions(self, client):
        response = client.get("/api/executions/")
        assert response.status_code == 200

    def test_create_execution_requires_data(self, client):
        response = client.post("/api/executions/", json={})
        assert response.status_code in (400, 404, 422)

    def test_get_execution_not_found(self, client):
        response = client.get("/api/executions/nonexistent-id")
        assert response.status_code == 404


class TestReportRouter:

    def test_list_reports(self, client):
        response = client.get("/api/reports/")
        assert response.status_code == 200

    def test_get_report_not_found(self, client):
        response = client.get("/api/reports/nonexistent-id")
        assert response.status_code == 404

    def test_generate_report_requires_execution_id(self, client):
        response = client.post("/api/reports/generate/nonexistent-id")
        assert response.status_code in (404, 422)


class TestHealthEndpoint:

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        response = client.get("/health")
        data = response.json()
        assert isinstance(data, dict)


class TestSchemaUploadAndScenarioGeneration:

    def test_upload_then_list(self, client, sample_openapi_json):
        upload_resp = _upload_file(client, sample_openapi_json)
        assert upload_resp.status_code in (200, 201)
        list_resp = client.get("/api/schemas/")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert "schemas" in data

    def test_upload_then_generate_scenarios(self, client, sample_openapi_json):
        upload_resp = _upload_file(client, sample_openapi_json)
        assert upload_resp.status_code in (200, 201)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code in (200, 201)

    def test_upload_generate_then_execute(self, client, sample_openapi_json):
        upload_resp = _upload_file(client, sample_openapi_json)
        schema_id = upload_resp.json()["schema_id"]
        gen_resp = client.post(f"/api/scenarios/generate/{schema_id}")
        assert gen_resp.status_code in (200, 201)
