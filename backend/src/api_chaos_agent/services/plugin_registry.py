"""Plugin registry with event-driven notifications.

Extends the core ``PluginManager`` with a publish/subscribe event bus
so that other subsystems can react to plugin lifecycle changes
(load / enable / disable / unload) without coupling to the manager.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.plugin import FaultPlugin, PluginStatus
from api_chaos_agent.models.scenario import ChaosScenario
from api_chaos_agent.services.plugin_framework import PluginManager

logger = get_logger(__name__)


class PluginEventType(StrEnum):
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNLOADED = "unloaded"
    ERROR = "error"


PluginEventHandler = Callable[[PluginEventType, str, dict[str, Any]], None]


class PluginRegistry:
    """Event-aware plugin registry wrapping PluginManager."""

    def __init__(self, manager: PluginManager | None = None) -> None:
        self._manager = manager or PluginManager()
        self._subscribers: list[PluginEventHandler] = []
        self._event_log: list[dict[str, Any]] = []

    @property
    def manager(self) -> PluginManager:
        return self._manager

    def subscribe(self, handler: PluginEventHandler) -> None:
        self._subscribers.append(handler)

    def unsubscribe(self, handler: PluginEventHandler) -> None:
        self._subscribers = [h for h in self._subscribers if h is not handler]

    def _emit(
        self, event_type: PluginEventType, plugin_name: str, payload: dict[str, Any] | None = None
    ) -> None:
        entry = {
            "event": event_type.value,
            "plugin": plugin_name,
            "timestamp": time.monotonic(),
            **(payload or {}),
        }
        self._event_log.append(entry)
        for handler in self._subscribers:
            try:
                handler(event_type, plugin_name, entry)
            except Exception:
                logger.warning("plugin_event_handler_error", handler=repr(handler))

    def load_from_directory(self, directory: str) -> list[FaultPlugin]:
        loaded = self._manager.load_from_directory(directory)
        for fp in loaded:
            self._emit(
                PluginEventType.LOADED, fp.manifest.name, {"source": "directory", "path": directory}
            )
        return loaded

    def load_from_entrypoint(self, module_path: str) -> FaultPlugin | None:
        fp = self._manager.load_from_entrypoint(module_path)
        if fp:
            self._emit(
                PluginEventType.LOADED,
                fp.manifest.name,
                {"source": "entrypoint", "path": module_path},
            )
        return fp

    def enable(self, name: str) -> bool:
        result = self._manager.enable(name)
        if result:
            self._emit(PluginEventType.ENABLED, name)
        return result

    def disable(self, name: str) -> bool:
        result = self._manager.disable(name)
        if result:
            self._emit(PluginEventType.DISABLED, name)
        return result

    def get(self, name: str) -> FaultPlugin | None:
        return self._manager.get(name)

    def list_plugins(self, status: PluginStatus | None = None) -> list[FaultPlugin]:
        return self._manager.list_plugins(status)

    async def execute(
        self, plugin_name: str, scenario: ChaosScenario, config: dict[str, Any]
    ) -> Any:
        return await self._manager.execute(plugin_name, scenario, config)

    def get_event_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._event_log[-limit:]
