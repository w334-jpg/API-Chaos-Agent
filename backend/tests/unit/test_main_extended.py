"""Extended tests for main.py — middleware, health, auth, websocket."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from api_chaos_agent.main import (
    RequestLoggingMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    _validate_security_config,
    _ws_add,
    _ws_remove,
    broadcast_progress,
)


class TestRequestSizeLimitMiddleware:
    @pytest.mark.asyncio
    async def test_allows_normal_request(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RequestSizeLimitMiddleware(MagicMock())

        async def call_next(request):
            return Response(content="ok", status_code=200)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"content-length", b"100")],
            "server": ("testserver", 80),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rejects_oversized_request(self):
        from starlette.requests import Request
        from starlette.responses import Response

        from api_chaos_agent.core.config import AppConfig, ServerConfig

        config = AppConfig(server=ServerConfig(max_request_body_size=100))

        middleware = RequestSizeLimitMiddleware(MagicMock())

        async def call_next(request):
            return Response(content="ok", status_code=200)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"content-length", b"999999999")],
            "server": ("testserver", 80),
        }
        request = Request(scope)

        with patch("api_chaos_agent.main.settings", config):
            response = await middleware.dispatch(request, call_next)
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_passes_through_invalid_content_length(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RequestSizeLimitMiddleware(MagicMock())

        async def call_next(request):
            return Response(content="ok", status_code=200)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"content-length", b"not-a-number")],
            "server": ("testserver", 80),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_passes_through_no_content_length(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RequestSizeLimitMiddleware(MagicMock())

        async def call_next(request):
            return Response(content="ok", status_code=200)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200


class TestSecurityHeadersMiddleware:
    @pytest.mark.asyncio
    async def test_adds_security_headers(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = SecurityHeadersMiddleware(MagicMock())

        async def call_next(request):
            return Response(content="ok", status_code=200)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, call_next)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Cache-Control"] == "no-store"
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers


class TestRequestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_logs_request(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RequestLoggingMiddleware(MagicMock())

        async def call_next(request):
            return Response(content="ok", status_code=200)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200


class TestValidateSecurityConfig:
    def test_raises_on_insecure_key_with_auth_enabled(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig

        config = AppConfig(
            auth=AuthConfig(
                enabled=True,
                secret_key="change-me-in-production-use-a-strong-key",
                admin_username="admin",
                admin_password="password",
            )
        )
        with patch("api_chaos_agent.main.settings", config):
            with pytest.raises(RuntimeError, match="insecure default"):
                _validate_security_config()

    def test_raises_on_missing_admin_credentials(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig

        config = AppConfig(
            auth=AuthConfig(
                enabled=True,
                secret_key="a" * 64,
                admin_username="",
                admin_password="",
            )
        )
        with patch("api_chaos_agent.main.settings", config):
            with pytest.raises(RuntimeError, match="ADMIN_USERNAME"):
                _validate_security_config()

    def test_passes_when_auth_disabled(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig

        config = AppConfig(auth=AuthConfig(enabled=False))
        with patch("api_chaos_agent.main.settings", config):
            _validate_security_config()

    def test_passes_with_valid_config(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig

        config = AppConfig(
            auth=AuthConfig(
                enabled=True,
                secret_key="a" * 64,
                admin_username="admin",
                admin_password="password",
            )
        )
        with patch("api_chaos_agent.main.settings", config):
            _validate_security_config()


class TestHealthEndpoints:
    def test_liveness_check(self):
        from api_chaos_agent.main import app

        client = TestClient(app)
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_check(self):
        from api_chaos_agent.main import app

        client = TestClient(app)
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_health_check(self):
        from api_chaos_agent.main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "checks" in data
        assert "auth_enabled" in data


class TestAuthEndpoint:
    def test_login_with_auth_disabled(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig
        from api_chaos_agent.main import app

        config = AppConfig(auth=AuthConfig(enabled=False))
        with patch("api_chaos_agent.main.settings", config):
            client = TestClient(app)
            response = client.post("/auth/token", data={"username": "any", "password": "any"})
            assert response.status_code == 200
            assert response.json()["access_token"] == "disabled"

    def test_login_with_valid_credentials(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig
        from api_chaos_agent.main import app

        config = AppConfig(
            auth=AuthConfig(
                enabled=True,
                secret_key="a" * 64,
                admin_username="admin",
                admin_password="password",
            )
        )
        with patch("api_chaos_agent.main.settings", config):
            client = TestClient(app)
            response = client.post("/auth/token", data={"username": "admin", "password": "password"})
            assert response.status_code == 200
            assert "access_token" in response.json()
            assert response.json()["token_type"] == "bearer"

    def test_login_with_invalid_credentials(self):
        from api_chaos_agent.core.config import AppConfig, AuthConfig
        from api_chaos_agent.main import app

        config = AppConfig(
            auth=AuthConfig(
                enabled=True,
                secret_key="a" * 64,
                admin_username="admin",
                admin_password="password",
            )
        )
        with patch("api_chaos_agent.main.settings", config):
            client = TestClient(app)
            response = client.post("/auth/token", data={"username": "wrong", "password": "wrong"})
            assert response.status_code == 401


class TestWebSocketHelpers:
    @pytest.mark.asyncio
    async def test_ws_add_and_remove(self):
        mock_ws = MagicMock()
        from api_chaos_agent.main import _ws_connections
        await _ws_add(mock_ws)
        assert mock_ws in _ws_connections
        await _ws_remove(mock_ws)
        assert mock_ws not in _ws_connections

    @pytest.mark.asyncio
    async def test_ws_remove_nonexistent(self):
        mock_ws = MagicMock()
        await _ws_remove(mock_ws)

    @pytest.mark.asyncio
    async def test_broadcast_progress_no_connections(self):
        await broadcast_progress("exec-1", {"progress": 50})

    @pytest.mark.asyncio
    async def test_broadcast_progress_with_connection(self):
        mock_ws = AsyncMock()
        from api_chaos_agent.main import _ws_connections
        _ws_connections.append(mock_ws)
        try:
            await broadcast_progress("exec-1", {"progress": 50})
            mock_ws.send_json.assert_called_once()
        finally:
            _ws_connections.remove(mock_ws)

    @pytest.mark.asyncio
    async def test_broadcast_progress_removes_dead_connection(self):
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("connection dead")
        from api_chaos_agent.main import _ws_connections
        _ws_connections.append(mock_ws)
        try:
            await broadcast_progress("exec-1", {"progress": 50})
            assert mock_ws not in _ws_connections
        finally:
            if mock_ws in _ws_connections:
                _ws_connections.remove(mock_ws)
