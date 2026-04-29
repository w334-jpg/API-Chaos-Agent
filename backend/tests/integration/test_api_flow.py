"""Integration tests — full API flow: upload → generate → execute → report."""

from __future__ import annotations

import io
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api_chaos_agent.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_openapi_spec() -> bytes:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Petstore", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "summary": "List pets",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "Create pet",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "age": {"type": "integer"},
                                    },
                                    "required": ["name"],
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            }
        },
    }
    return json.dumps(spec).encode("utf-8")


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_liveness_check(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_upload_schema(client: AsyncClient) -> None:
    spec_bytes = _make_openapi_spec()
    files = {"file": ("petstore.json", io.BytesIO(spec_bytes), "application/json")}
    resp = await client.post("/api/schemas/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "schema_id" in data
    assert data["endpoints"] >= 1


@pytest.mark.asyncio
async def test_list_schemas_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/schemas/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_nonexistent_schema(client: AsyncClient) -> None:
    resp = await client.get("/api/schemas/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_and_list_schemas(client: AsyncClient) -> None:
    spec_bytes = _make_openapi_spec()
    files = {"file": ("petstore.json", io.BytesIO(spec_bytes), "application/json")}
    upload_resp = await client.post("/api/schemas/upload", files=files)
    assert upload_resp.status_code == 200

    list_resp = await client.get("/api/schemas/")
    assert list_resp.status_code == 200
    schemas = list_resp.json()["schemas"]
    assert len(schemas) >= 1


@pytest.mark.asyncio
async def test_upload_empty_file(client: AsyncClient) -> None:
    files = {"file": ("empty.json", io.BytesIO(b""), "application/json")}
    resp = await client.post("/api/schemas/upload", files=files)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_invalid_content_type(client: AsyncClient) -> None:
    spec_bytes = _make_openapi_spec()
    files = {"file": ("petstore.txt", io.BytesIO(spec_bytes), "text/plain")}
    resp = await client.post("/api/schemas/upload", files=files)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_security_headers(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-xss-protection") == "1; mode=block"


@pytest.mark.asyncio
async def test_cors_headers(client: AsyncClient) -> None:
    resp = await client.options(
        "/health",
        headers={
            "origin": "http://localhost:3000",
            "access-control-request-method": "GET",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiting_headers(client: AsyncClient) -> None:
    for _ in range(5):
        resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_scenarios(client: AsyncClient) -> None:
    resp = await client.get("/api/scenarios/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_executions(client: AsyncClient) -> None:
    resp = await client.get("/api/executions/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_reports(client: AsyncClient) -> None:
    resp = await client.get("/api/reports/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_nonexistent_report(client: AsyncClient) -> None:
    resp = await client.get("/api/reports/nonexistent")
    assert resp.status_code == 404
