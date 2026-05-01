"""Tests for new quality improvement modules.

Covers:
- Dependency injection (core/deps.py)
- Global exception handlers (core/error_handlers.py)
- API versioning middleware (core/api_versioning.py)
- Plugin registry (services/plugin_registry.py)
- Config reloader (core/config_reloader.py)
- Sanitizer in-place optimization (core/sanitizer.py)
- Store async iterators (services/store.py)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


class TestDependencyInjection:
    def test_get_distributed_engine_returns_instance(self):
        from api_chaos_agent.core.deps import get_distributed_engine

        engine = get_distributed_engine()
        assert engine is not None

    def test_get_plugin_manager_returns_instance(self):
        from api_chaos_agent.core.deps import get_plugin_manager

        manager = get_plugin_manager()
        assert manager is not None

    def test_get_cicd_service_returns_instance(self):
        from api_chaos_agent.core.deps import get_cicd_service

        service = get_cicd_service()
        assert service is not None

    def test_get_tenant_service_returns_instance(self):
        from api_chaos_agent.core.deps import get_tenant_service

        service = get_tenant_service()
        assert service is not None

    def test_get_analytics_service_returns_instance(self):
        from api_chaos_agent.core.deps import get_analytics_service

        service = get_analytics_service()
        assert service is not None

    def test_get_store_returns_proxy(self):
        from api_chaos_agent.core.deps import get_store

        s = get_store()
        assert s is not None

    def test_lru_cache_returns_same_instance(self):
        from api_chaos_agent.core.deps import get_distributed_engine

        e1 = get_distributed_engine()
        e2 = get_distributed_engine()
        assert e1 is e2


class TestGlobalExceptionHandlers:
    def setup_method(self):
        self.app = FastAPI()
        from api_chaos_agent.core.error_handlers import register_exception_handlers

        register_exception_handlers(self.app)

        @self.app.get("/chaos-error")
        async def chaos_error():
            from api_chaos_agent.core.exceptions import ChaosAgentError

            raise ChaosAgentError(detail="test chaos error")

        @self.app.get("/validation-error")
        async def validation_error():
            raise ValidationError.from_exception_data(title="test", line_errors=[])

        @self.app.get("/unhandled-error")
        async def unhandled_error():
            raise RuntimeError("unexpected")

    def test_chaos_agent_error_returns_json(self):
        client = TestClient(self.app, raise_server_exceptions=False)
        resp = client.get("/chaos-error")
        assert resp.status_code == 500
        body = resp.json()
        assert "error" in body
        assert body["error"]["type"] == "ChaosAgentError"
        assert body["error"]["detail"] == "test chaos error"

    def test_unhandled_error_returns_json(self):
        client = TestClient(self.app, raise_server_exceptions=False)
        resp = client.get("/unhandled-error")
        assert resp.status_code == 500
        body = resp.json()
        assert "error" in body
        assert body["error"]["type"] == "InternalServerError"


class TestAPIVersioningMiddleware:
    def setup_method(self):
        self.app = FastAPI()
        from api_chaos_agent.core.api_versioning import APIVersionMiddleware

        self.app.add_middleware(APIVersionMiddleware)

        @self.app.get("/api/v2/test")
        async def v2_endpoint():
            return {"ok": True}

        @self.app.get("/api/schemas/test")
        async def legacy_endpoint():
            return {"ok": True}

    def test_v2_endpoint_has_version_header(self):
        client = TestClient(self.app)
        resp = client.get("/api/v2/test")
        assert resp.headers.get("X-API-Version") == "2.0.0"

    def test_legacy_endpoint_has_deprecation_headers(self):
        client = TestClient(self.app)
        resp = client.get("/api/schemas/test")
        assert resp.headers.get("Deprecation") == "true"
        assert resp.headers.get("Sunset") is not None
        assert "successor-version" in resp.headers.get("Link", "")


class TestPluginRegistry:
    def test_subscribe_and_emit(self):
        from api_chaos_agent.services.plugin_registry import PluginEventType, PluginRegistry

        registry = PluginRegistry()
        received = []
        registry.subscribe(lambda et, name, payload: received.append((et, name)))
        registry._emit(PluginEventType.ENABLED, "test_plugin")
        assert len(received) == 1
        assert received[0] == (PluginEventType.ENABLED, "test_plugin")

    def test_unsubscribe(self):
        from api_chaos_agent.services.plugin_registry import PluginEventType, PluginRegistry

        registry = PluginRegistry()
        received = []

        def handler(et, name, payload):
            return received.append((et, name))

        registry.subscribe(handler)
        registry._emit(PluginEventType.DISABLED, "p1")
        registry.unsubscribe(handler)
        registry._emit(PluginEventType.DISABLED, "p2")
        assert len(received) == 1

    def test_event_log(self):
        from api_chaos_agent.services.plugin_registry import PluginEventType, PluginRegistry

        registry = PluginRegistry()
        registry._emit(PluginEventType.LOADED, "p1")
        log = registry.get_event_log()
        assert len(log) == 1
        assert log[0]["event"] == "loaded"
        assert log[0]["plugin"] == "p1"

    def test_enable_delegates_to_manager(self):
        from api_chaos_agent.services.plugin_registry import PluginRegistry

        registry = PluginRegistry()
        result = registry.enable("resource_exhaustion")
        assert result is True

    def test_disable_delegates_to_manager(self):
        from api_chaos_agent.services.plugin_registry import PluginRegistry

        registry = PluginRegistry()
        result = registry.disable("resource_exhaustion")
        assert result is True

    def test_list_plugins(self):
        from api_chaos_agent.services.plugin_registry import PluginRegistry

        registry = PluginRegistry()
        plugins = registry.list_plugins()
        assert len(plugins) >= 4


class TestConfigReloader:
    def test_no_config_file_returns_false(self):
        from api_chaos_agent.core.config_reloader import ConfigReloader

        reloader = ConfigReloader()
        reloader._path = None
        assert reloader.check_and_reload() is False

    def test_nonexistent_path_returns_false(self):
        from pathlib import Path

        from api_chaos_agent.core.config_reloader import ConfigReloader

        reloader = ConfigReloader()
        reloader._path = Path("/nonexistent/config.json")
        assert reloader.check_and_reload() is False

    def test_register_callback(self):
        from api_chaos_agent.core.config_reloader import ConfigReloader

        reloader = ConfigReloader()
        called = []
        reloader.on_change("auth", lambda cfg: called.append(True))
        assert len(reloader._callbacks) == 1


class TestSanitizerInPlace:
    def test_sanitize_returns_same_dict_object(self):
        from api_chaos_agent.core.sanitizer import SchemaSanitizer

        s = SchemaSanitizer()
        spec = {"info": {"title": "Test", "version": "1.0"}, "paths": {}, "servers": []}
        result = s.sanitize(spec)
        assert result is spec

    def test_sanitize_redacts_email(self):
        from api_chaos_agent.core.sanitizer import SchemaSanitizer

        s = SchemaSanitizer()
        spec = {
            "info": {"title": "Test", "contact": {"email": "admin@example.com", "name": "Admin"}},
            "paths": {},
        }
        s.sanitize(spec)
        assert spec["info"]["contact"]["email"] == "[REDACTED]"
        assert spec["info"]["contact"]["name"] == "[REDACTED]"

    def test_sanitize_redacts_internal_hostname(self):
        from api_chaos_agent.core.sanitizer import SchemaSanitizer

        s = SchemaSanitizer()
        spec = {
            "servers": [{"url": "https://api.internal.corp:8080"}],
            "paths": {},
        }
        s.sanitize(spec)
        assert "[sanitized-host]" in spec["servers"][0]["url"]

    def test_sanitize_redacts_ip_address(self):
        from api_chaos_agent.core.sanitizer import SchemaSanitizer

        s = SchemaSanitizer()
        spec = {
            "servers": [{"url": "https://10.0.0.1:8080"}],
            "paths": {},
        }
        s.sanitize(spec)
        assert "[sanitized-ip]" in spec["servers"][0]["url"]

    def test_sanitize_redacts_sensitive_params(self):
        from api_chaos_agent.core.sanitizer import SchemaSanitizer

        s = SchemaSanitizer()
        spec = {
            "paths": {
                "/login": {
                    "post": {
                        "parameters": [
                            {
                                "name": "password",
                                "in": "query",
                                "schema": {"type": "string", "default": "secret123"},
                            }
                        ]
                    }
                }
            }
        }
        s.sanitize(spec)
        param = spec["paths"]["/login"]["post"]["parameters"][0]
        assert param["schema"]["default"] == "[REDACTED]"


class TestStoreIterators:
    @pytest.mark.asyncio
    async def test_iter_schemas_empty(self):
        from api_chaos_agent.services.store import InMemoryStore

        store = InMemoryStore()
        items = []
        async for key, value in store.iter_schemas():
            items.append((key, value))
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_iter_schemas_with_data(self):
        from api_chaos_agent.models.schema import APISpec
        from api_chaos_agent.services.store import InMemoryStore

        store = InMemoryStore()
        spec = APISpec(title="Test", version="1.0")
        schema_id = await store.save_schema(spec)
        items = []
        async for key, value in store.iter_schemas():
            items.append((key, value))
        assert len(items) == 1
        assert items[0][0] == schema_id

    @pytest.mark.asyncio
    async def test_iter_reports_empty(self):
        from api_chaos_agent.services.store import InMemoryStore

        store = InMemoryStore()
        items = []
        async for key, value in store.iter_reports():
            items.append((key, value))
        assert len(items) == 0


class TestExceptionHierarchy:
    def test_chaos_agent_error_has_detail(self):
        from api_chaos_agent.core.exceptions import ChaosAgentError

        err = ChaosAgentError(detail="something went wrong")
        assert err.detail == "something went wrong"

    def test_schema_parse_error_inherits(self):
        from api_chaos_agent.core.exceptions import ChaosAgentError, SchemaParseError

        err = SchemaParseError(detail="invalid spec")
        assert isinstance(err, ChaosAgentError)

    def test_execution_error_inherits(self):
        from api_chaos_agent.core.exceptions import ChaosAgentError, ExecutionError

        err = ExecutionError(detail="timeout")
        assert isinstance(err, ChaosAgentError)

    def test_plugin_error_inherits(self):
        from api_chaos_agent.core.exceptions import ChaosAgentError, PluginError

        err = PluginError(detail="load failed")
        assert isinstance(err, ChaosAgentError)


class TestSecurityHeaders:
    def setup_method(self):
        self.app = FastAPI()
        from api_chaos_agent.main import SecurityHeadersMiddleware

        self.app.add_middleware(SecurityHeadersMiddleware)

        @self.app.get("/test")
        async def test_endpoint():
            return {"ok": True}

    def test_csp_header_present(self):
        client = TestClient(self.app)
        resp = client.get("/test")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_permissions_policy_header(self):
        client = TestClient(self.app)
        resp = client.get("/test")
        pp = resp.headers.get("Permissions-Policy", "")
        assert "camera=()" in pp
        assert "microphone=()" in pp

    def test_x_content_type_options(self):
        client = TestClient(self.app)
        resp = client.get("/test")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self):
        client = TestClient(self.app)
        resp = client.get("/test")
        assert resp.headers.get("X-Frame-Options") == "DENY"
