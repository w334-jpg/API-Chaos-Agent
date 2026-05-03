"""Tests for PluginRegistry — event-driven plugin lifecycle management."""

from __future__ import annotations

from unittest.mock import MagicMock

from api_chaos_agent.models.plugin import FaultPlugin, FaultPluginManifest, PluginStatus
from api_chaos_agent.services.plugin_registry import PluginEventType, PluginRegistry


def _make_manifest(name: str = "test-plugin") -> FaultPluginManifest:
    return FaultPluginManifest(
        name=name,
        version="1.0.0",
        description="Test plugin",
        author="test",
        scenario_type="latency",
        entry_point="test_plugin:TestPlugin",
    )


def _make_plugin(name: str = "test-plugin") -> FaultPlugin:
    return FaultPlugin(manifest=_make_manifest(name))


class TestPluginRegistryInit:
    def test_init_with_manager(self):
        from api_chaos_agent.services.plugin_framework import PluginManager
        manager = PluginManager()
        registry = PluginRegistry(manager=manager)
        assert registry.manager is manager

    def test_init_without_manager(self):
        registry = PluginRegistry()
        assert registry.manager is not None


class TestPluginRegistrySubscribe:
    def test_subscribe(self):
        registry = PluginRegistry()
        handler = MagicMock()
        registry.subscribe(handler)
        assert handler in registry._subscribers

    def test_unsubscribe(self):
        registry = PluginRegistry()
        handler = MagicMock()
        registry.subscribe(handler)
        registry.unsubscribe(handler)
        assert handler not in registry._subscribers


class TestPluginRegistryEmit:
    def test_emit_calls_subscribers(self):
        registry = PluginRegistry()
        handler = MagicMock()
        registry.subscribe(handler)
        registry._emit(PluginEventType.LOADED, "test-plugin")
        handler.assert_called_once()

    def test_emit_logs_event(self):
        registry = PluginRegistry()
        registry._emit(PluginEventType.LOADED, "test-plugin", {"source": "directory"})
        assert len(registry._event_log) == 1
        entry = registry._event_log[0]
        assert entry["event"] == "loaded"
        assert entry["plugin"] == "test-plugin"
        assert entry["source"] == "directory"

    def test_emit_handles_subscriber_exception(self):
        registry = PluginRegistry()
        handler = MagicMock(side_effect=RuntimeError("handler error"))
        registry.subscribe(handler)
        registry._emit(PluginEventType.LOADED, "test-plugin")
        assert len(registry._event_log) == 1

    def test_emit_without_payload(self):
        registry = PluginRegistry()
        registry._emit(PluginEventType.ENABLED, "test-plugin")
        assert registry._event_log[0]["event"] == "enabled"


class TestPluginRegistryOperations:
    def test_enable_emits_event(self):
        registry = PluginRegistry()
        plugin = _make_plugin()
        registry._manager._plugins["test-plugin"] = plugin
        result = registry.enable("test-plugin")
        assert result is True
        assert any(e["event"] == "enabled" for e in registry._event_log)

    def test_enable_nonexistent_returns_false(self):
        registry = PluginRegistry()
        result = registry.enable("nonexistent")
        assert result is False

    def test_disable_emits_event(self):
        registry = PluginRegistry()
        plugin = _make_plugin()
        plugin.status = PluginStatus.ENABLED
        registry._manager._plugins["test-plugin"] = plugin
        result = registry.disable("test-plugin")
        assert result is True
        assert any(e["event"] == "disabled" for e in registry._event_log)

    def test_disable_nonexistent_returns_false(self):
        registry = PluginRegistry()
        result = registry.disable("nonexistent")
        assert result is False

    def test_get_returns_plugin(self):
        registry = PluginRegistry()
        plugin = _make_plugin()
        registry._manager._plugins["test-plugin"] = plugin
        assert registry.get("test-plugin") is plugin

    def test_get_nonexistent_returns_none(self):
        registry = PluginRegistry()
        assert registry.get("nonexistent") is None

    def test_list_plugins(self):
        registry = PluginRegistry()
        plugin = _make_plugin()
        registry._manager._plugins["test-plugin"] = plugin
        result = registry.list_plugins()
        assert any(p.manifest.name == "test-plugin" for p in result)

    def test_list_plugins_with_status_filter(self):
        registry = PluginRegistry()
        plugin = _make_plugin()
        plugin.status = PluginStatus.DISABLED
        registry._manager._plugins["test-plugin"] = plugin
        result = registry.list_plugins(status=PluginStatus.ENABLED)
        assert not any(p.manifest.name == "test-plugin" for p in result)
        result_all = registry.list_plugins(status=PluginStatus.DISABLED)
        assert any(p.manifest.name == "test-plugin" for p in result_all)


class TestPluginRegistryGetEventLog:
    def test_get_event_log_default_limit(self):
        registry = PluginRegistry()
        for i in range(150):
            registry._emit(PluginEventType.LOADED, f"plugin-{i}")
        log = registry.get_event_log()
        assert len(log) == 100

    def test_get_event_log_custom_limit(self):
        registry = PluginRegistry()
        for i in range(20):
            registry._emit(PluginEventType.LOADED, f"plugin-{i}")
        log = registry.get_event_log(limit=10)
        assert len(log) == 10

    def test_get_event_log_empty(self):
        registry = PluginRegistry()
        log = registry.get_event_log()
        assert len(log) == 0
