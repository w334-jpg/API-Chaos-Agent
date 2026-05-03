"""Tests for scenarios and plugins routers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from api_chaos_agent.main import app


class TestScenariosRouter:
    def test_list_scenarios(self):
        client = TestClient(app)
        with patch("api_chaos_agent.routers.scenarios.CurrentUser", return_value="test-user"):
            response = client.get("/api/scenarios/")
            assert response.status_code in (200, 401)

    def test_get_scenario_not_found(self):
        client = TestClient(app)
        with patch("api_chaos_agent.routers.scenarios.CurrentUser", return_value="test-user"):
            response = client.get("/api/scenarios/nonexistent-id")
            assert response.status_code in (404, 401)

    def test_generate_scenarios_schema_not_found(self):
        client = TestClient(app)
        with patch("api_chaos_agent.routers.scenarios.CurrentUser", return_value="test-user"):
            response = client.post("/api/scenarios/generate/nonexistent-schema")
            assert response.status_code in (404, 401)

    def test_generate_scenarios_id_too_long(self):
        client = TestClient(app)
        with patch("api_chaos_agent.routers.scenarios.CurrentUser", return_value="test-user"):
            response = client.post(f"/api/scenarios/generate/{'x' * 300}")
            assert response.status_code in (400, 401)

    def test_execute_scenarios_empty_list(self):
        client = TestClient(app)
        with patch("api_chaos_agent.routers.scenarios.CurrentUser", return_value="test-user"):
            response = client.post(
                "/api/scenarios/execute",
                json={"scenario_ids": [], "base_url": "http://localhost"},
            )
            assert response.status_code in (400, 401, 422)


class TestPluginsRouter:
    def test_list_plugins(self):
        client = TestClient(app)
        response = client.get("/api/v2/plugins")
        assert response.status_code in (200, 401)

    def test_get_plugin_not_found(self):
        client = TestClient(app)
        response = client.get("/api/v2/plugins/nonexistent-plugin")
        assert response.status_code in (404, 401)

    def test_enable_plugin_not_found(self):
        client = TestClient(app)
        response = client.post("/api/v2/plugins/nonexistent-plugin/enable")
        assert response.status_code in (404, 401)

    def test_disable_plugin_not_found(self):
        client = TestClient(app)
        response = client.post("/api/v2/plugins/nonexistent-plugin/disable")
        assert response.status_code in (404, 401)

    def test_execute_plugin_not_found(self):
        client = TestClient(app)
        response = client.post(
            "/api/v2/plugins/nonexistent-plugin/execute",
            json={"scenario_id": "test", "config": {}},
        )
        assert response.status_code in (404, 401, 422)

    def test_validate_plugin_directory_allowed(self):
        from pathlib import Path

        from api_chaos_agent.routers.plugins import _validate_plugin_directory

        allowed_dir = str(Path.cwd() / "plugins")
        with patch("api_chaos_agent.routers.plugins._ALLOWED_PLUGIN_DIRS", [allowed_dir]):
            result = _validate_plugin_directory(allowed_dir)
            assert result is not None

    def test_validate_plugin_directory_blocked(self):
        from api_chaos_agent.core.exceptions import SecurityError
        from api_chaos_agent.routers.plugins import _validate_plugin_directory

        with patch("api_chaos_agent.routers.plugins._ALLOWED_PLUGIN_DIRS", ["/safe/dir"]):
            with pytest.raises(SecurityError):
                _validate_plugin_directory("/etc/passwd")

    def test_load_from_directory(self):
        client = TestClient(app)
        response = client.post(
            "/api/v2/plugins/load/directory",
            json={"directory": "/tmp/plugins"},
        )
        assert response.status_code in (200, 401, 403, 422)

    def test_load_from_entrypoint(self):
        client = TestClient(app)
        response = client.post(
            "/api/v2/plugins/load/entrypoint",
            json={"module_path": "nonexistent:Plugin"},
        )
        assert response.status_code in (400, 401, 422)
