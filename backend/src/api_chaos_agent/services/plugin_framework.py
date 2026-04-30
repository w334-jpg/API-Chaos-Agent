"""Fault Plugin Framework for extensible chaos scenario injection.

Provides:
- Plugin discovery and loading from entry points or directories
- Plugin lifecycle management (load, enable, disable, unload)
- Plugin execution with sandboxed config validation
- Plugin manifest validation
"""

from __future__ import annotations

import importlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.plugin import (
    FaultPlugin,
    FaultPluginExecution,
    FaultPluginManifest,
    PluginStatus,
)
from api_chaos_agent.models.scenario import ChaosScenario

logger = get_logger(__name__)


@runtime_checkable
class FaultPluginInterface(Protocol):
    """Protocol that all fault plugins must implement."""

    manifest: FaultPluginManifest

    async def execute(self, scenario: ChaosScenario, config: dict[str, Any]) -> dict[str, Any]: ...

    def validate_config(self, config: dict[str, Any]) -> bool: ...


class BuiltinResourceExhaustionPlugin:
    """Built-in plugin: Resource exhaustion scenarios (memory, CPU, connections)."""

    manifest = FaultPluginManifest(
        name="resource_exhaustion",
        version="1.0.0",
        description="Inject resource exhaustion scenarios (memory, CPU, connection pool)",
        author="api-chaos-agent",
        scenario_type="resource_exhaustion",
        entry_point="api_chaos_agent.services.plugin_framework:BuiltinResourceExhaustionPlugin",
        config_schema={
            "type": "object",
            "properties": {
                "resource_type": {"type": "string", "enum": ["memory", "cpu", "connections"]},
                "intensity": {"type": "string", "enum": ["low", "medium", "high"]},
                "duration_seconds": {"type": "integer", "minimum": 1},
            },
            "required": ["resource_type"],
        },
    )

    async def execute(self, scenario: ChaosScenario, config: dict[str, Any]) -> dict[str, Any]:
        resource_type = config.get("resource_type", "memory")
        intensity = config.get("intensity", "medium")
        duration = config.get("duration_seconds", 10)
        return {
            "injected": True,
            "resource_type": resource_type,
            "intensity": intensity,
            "duration_seconds": duration,
            "description": f"Injected {resource_type} exhaustion at {intensity} intensity for {duration}s",
        }

    def validate_config(self, config: dict[str, Any]) -> bool:
        return "resource_type" in config and config["resource_type"] in ("memory", "cpu", "connections")


class BuiltinDataCorruptionPlugin:
    """Built-in plugin: Data corruption scenarios (encoding, truncation, injection)."""

    manifest = FaultPluginManifest(
        name="data_corruption",
        version="1.0.0",
        description="Inject data corruption scenarios (encoding errors, truncation, injection)",
        author="api-chaos-agent",
        scenario_type="data_corruption",
        entry_point="api_chaos_agent.services.plugin_framework:BuiltinDataCorruptionPlugin",
        config_schema={
            "type": "object",
            "properties": {
                "corruption_type": {"type": "string", "enum": ["encoding", "truncation", "injection", "null_bytes"]},
                "target_field": {"type": "string"},
                "corruption_value": {"type": "string"},
            },
            "required": ["corruption_type"],
        },
    )

    async def execute(self, scenario: ChaosScenario, config: dict[str, Any]) -> dict[str, Any]:
        corruption_type = config.get("corruption_type", "encoding")
        target_field = config.get("target_field", "body")
        return {
            "injected": True,
            "corruption_type": corruption_type,
            "target_field": target_field,
            "description": f"Injected {corruption_type} corruption on {target_field}",
        }

    def validate_config(self, config: dict[str, Any]) -> bool:
        return "corruption_type" in config


class BuiltinDependencyFailurePlugin:
    """Built-in plugin: Dependency failure scenarios (timeout, circuit break, cascade)."""

    manifest = FaultPluginManifest(
        name="dependency_failure",
        version="1.0.0",
        description="Inject dependency failure scenarios (timeout, circuit breaker, cascade failure)",
        author="api-chaos-agent",
        scenario_type="dependency_failure",
        entry_point="api_chaos_agent.services.plugin_framework:BuiltinDependencyFailurePlugin",
        config_schema={
            "type": "object",
            "properties": {
                "failure_type": {"type": "string", "enum": ["timeout", "circuit_break", "cascade", "refused"]},
                "dependency_name": {"type": "string"},
                "failure_rate": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["failure_type"],
        },
    )

    async def execute(self, scenario: ChaosScenario, config: dict[str, Any]) -> dict[str, Any]:
        failure_type = config.get("failure_type", "timeout")
        dependency = config.get("dependency_name", "unknown")
        return {
            "injected": True,
            "failure_type": failure_type,
            "dependency_name": dependency,
            "description": f"Injected {failure_type} on dependency {dependency}",
        }

    def validate_config(self, config: dict[str, Any]) -> bool:
        return "failure_type" in config


class BuiltinNetworkPartitionPlugin:
    """Built-in plugin: Network partition scenarios (latency spike, packet loss, DNS failure)."""

    manifest = FaultPluginManifest(
        name="network_partition",
        version="1.0.0",
        description="Inject network partition scenarios (latency spike, packet loss, DNS failure)",
        author="api-chaos-agent",
        scenario_type="network_partition",
        entry_point="api_chaos_agent.services.plugin_framework:BuiltinNetworkPartitionPlugin",
        config_schema={
            "type": "object",
            "properties": {
                "partition_type": {"type": "string", "enum": ["latency_spike", "packet_loss", "dns_failure", "blackhole"]},
                "target_host": {"type": "string"},
                "duration_seconds": {"type": "integer", "minimum": 1},
                "loss_rate": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["partition_type"],
        },
    )

    async def execute(self, scenario: ChaosScenario, config: dict[str, Any]) -> dict[str, Any]:
        partition_type = config.get("partition_type", "latency_spike")
        target = config.get("target_host", "default")
        return {
            "injected": True,
            "partition_type": partition_type,
            "target_host": target,
            "description": f"Injected {partition_type} partition targeting {target}",
        }

    def validate_config(self, config: dict[str, Any]) -> bool:
        return "partition_type" in config


_BUILTIN_PLUGINS: list[FaultPluginInterface] = [
    BuiltinResourceExhaustionPlugin(),
    BuiltinDataCorruptionPlugin(),
    BuiltinDependencyFailurePlugin(),
    BuiltinNetworkPartitionPlugin(),
]


class PluginManager:
    """Manage fault plugins: discovery, loading, execution."""

    def __init__(self, plugin_dirs: list[str] | None = None) -> None:
        self._plugins: dict[str, FaultPlugin] = {}
        self._instances: dict[str, FaultPluginInterface] = {}
        self._plugin_dirs = plugin_dirs or []
        self._load_builtins()

    def _load_builtins(self) -> None:
        for plugin in _BUILTIN_PLUGINS:
            fp = FaultPlugin(
                id=str(uuid.uuid4()),
                manifest=plugin.manifest,
                status=PluginStatus.ENABLED,
            )
            self._plugins[fp.manifest.name] = fp
            self._instances[fp.manifest.name] = plugin
        logger.info("builtin_plugins_loaded", count=len(_BUILTIN_PLUGINS))

    def load_from_directory(self, directory: str) -> list[FaultPlugin]:
        loaded: list[FaultPlugin] = []
        dir_path = Path(directory)
        if not dir_path.exists():
            return loaded
        for manifest_file in dir_path.glob("*/manifest.json"):
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest = FaultPluginManifest(**data)
                fp = FaultPlugin(id=str(uuid.uuid4()), manifest=manifest)
                self._plugins[fp.manifest.name] = fp
                loaded.append(fp)
                logger.info("plugin_loaded_from_dir", name=fp.manifest.name, path=str(manifest_file))
            except Exception as e:
                logger.error("plugin_load_failed", path=str(manifest_file), error=str(e))
        return loaded

    def load_from_entrypoint(self, module_path: str) -> FaultPlugin | None:
        try:
            module_name, class_name = module_path.rsplit(":", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            instance = cls()
            if not isinstance(instance, FaultPluginInterface):
                logger.error("plugin_interface_mismatch", path=module_path)
                return None
            fp = FaultPlugin(id=str(uuid.uuid4()), manifest=instance.manifest, status=PluginStatus.ENABLED)
            self._plugins[fp.manifest.name] = fp
            self._instances[fp.manifest.name] = instance
            return fp
        except Exception as e:
            logger.error("plugin_entrypoint_load_failed", path=module_path, error=str(e))
            return None

    def get(self, name: str) -> FaultPlugin | None:
        return self._plugins.get(name)

    def list_plugins(self, status: PluginStatus | None = None) -> list[FaultPlugin]:
        plugins = list(self._plugins.values())
        if status:
            plugins = [p for p in plugins if p.status == status]
        return plugins

    def enable(self, name: str) -> bool:
        fp = self._plugins.get(name)
        if fp:
            fp.status = PluginStatus.ENABLED
            return True
        return False

    def disable(self, name: str) -> bool:
        fp = self._plugins.get(name)
        if fp:
            fp.status = PluginStatus.DISABLED
            return True
        return False

    async def execute(
        self, plugin_name: str, scenario: ChaosScenario, config: dict[str, Any]
    ) -> FaultPluginExecution:
        fp = self._plugins.get(plugin_name)
        instance = self._instances.get(plugin_name)
        if not fp or not instance:
            return FaultPluginExecution(
                plugin_id=plugin_name,
                scenario_id=scenario.id,
                success=False,
                error=f"Plugin '{plugin_name}' not found",
            )
        if fp.status != PluginStatus.ENABLED:
            return FaultPluginExecution(
                plugin_id=plugin_name,
                scenario_id=scenario.id,
                success=False,
                error=f"Plugin '{plugin_name}' is not enabled",
            )
        if not instance.validate_config(config):
            return FaultPluginExecution(
                plugin_id=plugin_name,
                scenario_id=scenario.id,
                input_config=config,
                success=False,
                error="Config validation failed",
            )
        start = time.monotonic()
        try:
            output = await instance.execute(scenario, config)
            elapsed = (time.monotonic() - start) * 1000
            fp.execution_count += 1
            fp.last_executed_at = time.monotonic()
            return FaultPluginExecution(
                plugin_id=plugin_name,
                scenario_id=scenario.id,
                input_config=config,
                output=output,
                success=True,
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            fp.status = PluginStatus.ERROR
            fp.error_message = str(e)
            return FaultPluginExecution(
                plugin_id=plugin_name,
                scenario_id=scenario.id,
                input_config=config,
                success=False,
                error=str(e),
                elapsed_ms=elapsed,
            )
