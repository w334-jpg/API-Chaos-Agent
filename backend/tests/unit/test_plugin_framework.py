"""Enhanced TDD tests for Phase 2: Fault Plugin Framework.

Covers: unit tests, functional tests, edge cases, stress tests.
"""

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, patch

import pytest

from api_chaos_agent.models.plugin import (
    PluginStatus,
)
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Endpoint
from api_chaos_agent.services.plugin_framework import (
    BuiltinDataCorruptionPlugin,
    BuiltinDependencyFailurePlugin,
    BuiltinNetworkPartitionPlugin,
    BuiltinResourceExhaustionPlugin,
    FaultPluginInterface,
    PluginManager,
)

_DEFAULT_ENDPOINT = Endpoint(path="/api/test", method="GET")


def _make_scenario(
    idx: int = 0, stype: ChaosScenarioType = ChaosScenarioType.LATENCY
) -> ChaosScenario:
    return ChaosScenario(
        id=f"s{idx}", name=f"scenario-{idx}", scenario_type=stype, endpoint=_DEFAULT_ENDPOINT
    )


class TestPluginManagerUnit:
    def setup_method(self):
        self.manager = PluginManager()

    def test_builtin_plugins_loaded(self):
        plugins = self.manager.list_plugins()
        assert len(plugins) >= 4
        names = {p.manifest.name for p in plugins}
        assert "resource_exhaustion" in names
        assert "data_corruption" in names
        assert "dependency_failure" in names
        assert "network_partition" in names

    def test_get_plugin(self):
        plugin = self.manager.get("resource_exhaustion")
        assert plugin is not None
        assert plugin.manifest.name == "resource_exhaustion"
        assert plugin.manifest.version == "1.0.0"

    def test_get_nonexistent_plugin(self):
        assert self.manager.get("nonexistent") is None

    def test_enable_plugin(self):
        self.manager.disable("resource_exhaustion")
        assert self.manager.enable("resource_exhaustion")
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.status == PluginStatus.ENABLED

    def test_disable_plugin(self):
        assert self.manager.disable("resource_exhaustion")
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.status == PluginStatus.DISABLED

    def test_enable_nonexistent(self):
        assert not self.manager.enable("nonexistent")

    def test_disable_nonexistent(self):
        assert not self.manager.disable("nonexistent")

    def test_list_plugins_all(self):
        plugins = self.manager.list_plugins()
        assert len(plugins) >= 4

    def test_list_plugins_by_status_enabled(self):
        enabled = self.manager.list_plugins(status=PluginStatus.ENABLED)
        assert len(enabled) >= 4

    def test_list_plugins_by_status_disabled(self):
        self.manager.disable("resource_exhaustion")
        disabled = self.manager.list_plugins(status=PluginStatus.DISABLED)
        assert len(disabled) == 1
        assert disabled[0].manifest.name == "resource_exhaustion"

    def test_list_plugins_by_status_error(self):
        errors = self.manager.list_plugins(status=PluginStatus.ERROR)
        assert len(errors) == 0

    def test_plugin_has_id(self):
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.id is not None
        assert len(plugin.id) > 0

    def test_plugin_ids_are_unique(self):
        plugins = self.manager.list_plugins()
        ids = [p.id for p in plugins]
        assert len(set(ids)) == len(ids)

    def test_plugin_manifest_fields(self):
        plugin = self.manager.get("resource_exhaustion")
        m = plugin.manifest
        assert m.name == "resource_exhaustion"
        assert m.version == "1.0.0"
        assert m.description is not None
        assert m.author == "api-chaos-agent"
        assert m.scenario_type == "resource_exhaustion"
        assert m.entry_point is not None
        assert m.config_schema is not None

    def test_plugin_default_execution_count(self):
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.execution_count == 0

    def test_plugin_default_last_executed_at(self):
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.last_executed_at is None

    def test_plugin_default_error_message(self):
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.error_message is None


class TestPluginExecution:
    def setup_method(self):
        self.manager = PluginManager()

    @pytest.mark.asyncio
    async def test_execute_resource_exhaustion(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "memory", "intensity": "high"}
        )
        assert result.success
        assert result.output["injected"]
        assert result.output["resource_type"] == "memory"
        assert result.output["intensity"] == "high"

    @pytest.mark.asyncio
    async def test_execute_resource_exhaustion_cpu(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "cpu"}
        )
        assert result.success
        assert result.output["resource_type"] == "cpu"

    @pytest.mark.asyncio
    async def test_execute_resource_exhaustion_connections(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "connections"}
        )
        assert result.success
        assert result.output["resource_type"] == "connections"

    @pytest.mark.asyncio
    async def test_execute_data_corruption_encoding(self):
        scenario = _make_scenario(0, ChaosScenarioType.DATA_CORRUPTION)
        result = await self.manager.execute(
            "data_corruption", scenario, {"corruption_type": "encoding"}
        )
        assert result.success
        assert result.output["corruption_type"] == "encoding"

    @pytest.mark.asyncio
    async def test_execute_data_corruption_truncation(self):
        scenario = _make_scenario(0, ChaosScenarioType.DATA_CORRUPTION)
        result = await self.manager.execute(
            "data_corruption", scenario, {"corruption_type": "truncation", "target_field": "body"}
        )
        assert result.success
        assert result.output["target_field"] == "body"

    @pytest.mark.asyncio
    async def test_execute_dependency_failure_timeout(self):
        scenario = _make_scenario(0, ChaosScenarioType.DEPENDENCY_FAILURE)
        result = await self.manager.execute(
            "dependency_failure", scenario, {"failure_type": "timeout"}
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_dependency_failure_circuit_break(self):
        scenario = _make_scenario(0, ChaosScenarioType.DEPENDENCY_FAILURE)
        result = await self.manager.execute(
            "dependency_failure", scenario, {"failure_type": "circuit_break"}
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_network_partition_packet_loss(self):
        scenario = _make_scenario(0, ChaosScenarioType.NETWORK_PARTITION)
        result = await self.manager.execute(
            "network_partition", scenario, {"partition_type": "packet_loss"}
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_network_partition_dns_failure(self):
        scenario = _make_scenario(0, ChaosScenarioType.NETWORK_PARTITION)
        result = await self.manager.execute(
            "network_partition", scenario, {"partition_type": "dns_failure"}
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_disabled_plugin_fails(self):
        self.manager.disable("resource_exhaustion")
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "memory"}
        )
        assert not result.success
        assert "not enabled" in result.error

    @pytest.mark.asyncio
    async def test_execute_nonexistent_plugin(self):
        scenario = _make_scenario()
        result = await self.manager.execute("nonexistent", scenario, {})
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_invalid_config(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"invalid_key": "value"}
        )
        assert not result.success
        assert "validation" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_increments_count(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.execution_count == 0
        await self.manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        assert plugin.execution_count == 1
        await self.manager.execute("resource_exhaustion", scenario, {"resource_type": "cpu"})
        assert plugin.execution_count == 2

    @pytest.mark.asyncio
    async def test_execute_sets_last_executed_at(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.last_executed_at is None
        await self.manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        assert plugin.last_executed_at is not None

    @pytest.mark.asyncio
    async def test_execution_result_has_elapsed_ms(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "memory"}
        )
        assert result.success
        assert result.elapsed_ms is not None
        assert result.elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_execution_result_has_scenario_id(self):
        scenario = _make_scenario(42, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await self.manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "memory"}
        )
        assert result.scenario_id == "s42"

    @pytest.mark.asyncio
    async def test_execution_result_has_input_config(self):
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        config = {"resource_type": "memory", "intensity": "low"}
        result = await self.manager.execute("resource_exhaustion", scenario, config)
        assert result.input_config == config

    @pytest.mark.asyncio
    async def test_execution_result_on_exception(self):
        instance = self.manager._instances["resource_exhaustion"]
        with patch.object(
            instance, "execute", new_callable=AsyncMock, side_effect=RuntimeError("boom")
        ):
            scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
            result = await self.manager.execute(
                "resource_exhaustion", scenario, {"resource_type": "memory"}
            )
            assert not result.success
            assert "boom" in result.error
            plugin = self.manager.get("resource_exhaustion")
            assert plugin.status == PluginStatus.ERROR
            assert plugin.error_message == "boom"


class TestPluginValidation:
    def test_resource_exhaustion_valid_configs(self):
        plugin = BuiltinResourceExhaustionPlugin()
        assert plugin.validate_config({"resource_type": "memory"})
        assert plugin.validate_config({"resource_type": "cpu"})
        assert plugin.validate_config({"resource_type": "connections"})

    def test_resource_exhaustion_invalid_configs(self):
        plugin = BuiltinResourceExhaustionPlugin()
        assert not plugin.validate_config({})
        assert not plugin.validate_config({"resource_type": "invalid"})
        assert not plugin.validate_config({"resource_type": ""})

    def test_data_corruption_valid_configs(self):
        plugin = BuiltinDataCorruptionPlugin()
        assert plugin.validate_config({"corruption_type": "encoding"})
        assert plugin.validate_config({"corruption_type": "truncation"})
        assert plugin.validate_config({"corruption_type": "injection"})
        assert plugin.validate_config({"corruption_type": "null_bytes"})

    def test_data_corruption_invalid_configs(self):
        plugin = BuiltinDataCorruptionPlugin()
        assert not plugin.validate_config({})
        assert not plugin.validate_config({"target_field": "body"})

    def test_dependency_failure_valid_configs(self):
        plugin = BuiltinDependencyFailurePlugin()
        assert plugin.validate_config({"failure_type": "timeout"})
        assert plugin.validate_config({"failure_type": "circuit_break"})
        assert plugin.validate_config({"failure_type": "cascade"})
        assert plugin.validate_config({"failure_type": "refused"})

    def test_dependency_failure_invalid_configs(self):
        plugin = BuiltinDependencyFailurePlugin()
        assert not plugin.validate_config({})
        assert not plugin.validate_config({"dependency_name": "db"})

    def test_network_partition_valid_configs(self):
        plugin = BuiltinNetworkPartitionPlugin()
        assert plugin.validate_config({"partition_type": "latency_spike"})
        assert plugin.validate_config({"partition_type": "packet_loss"})
        assert plugin.validate_config({"partition_type": "dns_failure"})
        assert plugin.validate_config({"partition_type": "blackhole"})

    def test_network_partition_invalid_configs(self):
        plugin = BuiltinNetworkPartitionPlugin()
        assert not plugin.validate_config({})
        assert not plugin.validate_config({"target_host": "example.com"})


class TestPluginLoading:
    def setup_method(self):
        self.manager = PluginManager()

    def test_load_from_nonexistent_directory(self):
        loaded = self.manager.load_from_directory("/nonexistent/path")
        assert loaded == []

    def test_load_from_directory_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = os.path.join(tmpdir, "test_plugin")
            os.makedirs(plugin_dir)
            manifest = {
                "name": "test_custom",
                "version": "1.0.0",
                "description": "Test plugin",
                "author": "tester",
                "scenario_type": "custom",
                "entry_point": "test:TestPlugin",
            }
            with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
                json.dump(manifest, f)
            loaded = self.manager.load_from_directory(tmpdir)
            assert len(loaded) == 1
            assert loaded[0].manifest.name == "test_custom"
            assert self.manager.get("test_custom") is not None

    def test_load_from_directory_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = os.path.join(tmpdir, "bad_plugin")
            os.makedirs(plugin_dir)
            with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
                f.write("not valid json{{{")
            loaded = self.manager.load_from_directory(tmpdir)
            assert loaded == []

    def test_load_from_directory_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = os.path.join(tmpdir, "incomplete")
            os.makedirs(plugin_dir)
            with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
                json.dump({"name": "incomplete"}, f)
            loaded = self.manager.load_from_directory(tmpdir)
            assert loaded == []

    def test_load_from_entrypoint_valid(self):
        result = self.manager.load_from_entrypoint(
            "api_chaos_agent.services.plugin_framework:BuiltinResourceExhaustionPlugin"
        )
        assert result is not None
        assert result.manifest.name == "resource_exhaustion"

    def test_load_from_entrypoint_invalid_module(self):
        result = self.manager.load_from_entrypoint("nonexistent.module:SomeClass")
        assert result is None

    def test_load_from_entrypoint_invalid_format(self):
        result = self.manager.load_from_entrypoint("no_colon_separator")
        assert result is None

    def test_load_from_entrypoint_nonexistent_class(self):
        result = self.manager.load_from_entrypoint(
            "api_chaos_agent.services.plugin_framework:NonexistentClass"
        )
        assert result is None

    def test_load_from_directory_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = os.path.join(tmpdir, "resource_exhaustion")
            os.makedirs(plugin_dir)
            manifest = {
                "name": "resource_exhaustion",
                "version": "2.0.0",
                "description": "Overwritten",
                "author": "test",
                "scenario_type": "resource_exhaustion",
                "entry_point": "test:Test",
            }
            with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
                json.dump(manifest, f)
            self.manager.load_from_directory(tmpdir)
            plugin = self.manager.get("resource_exhaustion")
            assert plugin.manifest.version == "2.0.0"

    def test_load_multiple_plugins_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["plugin_a", "plugin_b", "plugin_c"]:
                plugin_dir = os.path.join(tmpdir, name)
                os.makedirs(plugin_dir)
                manifest = {
                    "name": name,
                    "version": "1.0.0",
                    "description": f"Test {name}",
                    "author": "tester",
                    "scenario_type": "custom",
                    "entry_point": f"test:{name}",
                }
                with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
                    json.dump(manifest, f)
            loaded = self.manager.load_from_directory(tmpdir)
            assert len(loaded) == 3


class TestPluginInterface:
    def test_builtin_plugins_implement_interface(self):
        for plugin_cls in [
            BuiltinResourceExhaustionPlugin,
            BuiltinDataCorruptionPlugin,
            BuiltinDependencyFailurePlugin,
            BuiltinNetworkPartitionPlugin,
        ]:
            instance = plugin_cls()
            assert isinstance(instance, FaultPluginInterface)
            assert hasattr(instance, "manifest")
            assert hasattr(instance, "execute")
            assert hasattr(instance, "validate_config")

    def test_manifest_is_valid_model(self):
        plugin = BuiltinResourceExhaustionPlugin()
        m = plugin.manifest
        data = m.model_dump()
        assert "name" in data
        assert "version" in data
        assert data["name"] == "resource_exhaustion"


class TestPluginStress:
    @pytest.mark.asyncio
    async def test_execute_many_times(self):
        manager = PluginManager()
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        config = {"resource_type": "memory"}
        start = time.monotonic()
        for _ in range(100):
            result = await manager.execute("resource_exhaustion", scenario, config)
            assert result.success
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"100 executions took {elapsed:.3f}s"
        plugin = manager.get("resource_exhaustion")
        assert plugin.execution_count == 100

    @pytest.mark.asyncio
    async def test_execute_all_builtins_sequentially(self):
        manager = PluginManager()
        scenario = _make_scenario()
        configs = {
            "resource_exhaustion": {"resource_type": "memory"},
            "data_corruption": {"corruption_type": "encoding"},
            "dependency_failure": {"failure_type": "timeout"},
            "network_partition": {"partition_type": "packet_loss"},
        }
        for name, config in configs.items():
            result = await manager.execute(name, scenario, config)
            assert result.success, f"Plugin {name} failed: {result.error}"

    @pytest.mark.asyncio
    async def test_execute_many_plugins_concurrently(self):
        manager = PluginManager()
        scenario = _make_scenario()
        config = {"resource_type": "memory"}
        tasks = [manager.execute("resource_exhaustion", scenario, config) for _ in range(50)]
        results = await asyncio.gather(*tasks)
        assert all(r.success for r in results)
        plugin = manager.get("resource_exhaustion")
        assert plugin.execution_count == 50

    def test_load_many_manifests_from_directory(self):
        manager = PluginManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(50):
                plugin_dir = os.path.join(tmpdir, f"plugin_{i}")
                os.makedirs(plugin_dir)
                manifest = {
                    "name": f"custom_plugin_{i}",
                    "version": "1.0.0",
                    "description": f"Custom plugin {i}",
                    "author": "tester",
                    "scenario_type": "custom",
                    "entry_point": f"test:Plugin{i}",
                }
                with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
                    json.dump(manifest, f)
            start = time.monotonic()
            loaded = manager.load_from_directory(tmpdir)
            elapsed = time.monotonic() - start
            assert len(loaded) == 50
            assert elapsed < 2.0, f"Loading 50 plugins took {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_enable_disable_cycles(self):
        manager = PluginManager()
        for _ in range(100):
            manager.disable("resource_exhaustion")
            manager.enable("resource_exhaustion")
        plugin = manager.get("resource_exhaustion")
        assert plugin.status == PluginStatus.ENABLED


class TestPluginFunctional:
    @pytest.mark.asyncio
    async def test_full_plugin_lifecycle(self):
        manager = PluginManager()
        plugin = manager.get("resource_exhaustion")
        assert plugin.status == PluginStatus.ENABLED
        assert plugin.execution_count == 0
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        assert result.success
        assert plugin.execution_count == 1
        manager.disable("resource_exhaustion")
        result = await manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        assert not result.success
        manager.enable("resource_exhaustion")
        result = await manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        assert result.success
        assert plugin.execution_count == 2

    @pytest.mark.asyncio
    async def test_execution_result_serialization(self):
        manager = PluginManager()
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        data = result.model_dump()
        assert data["success"] is True
        assert data["plugin_id"] == "resource_exhaustion"
        assert data["scenario_id"] == "s0"

    @pytest.mark.asyncio
    async def test_custom_plugin_via_entrypoint(self):
        manager = PluginManager()
        loaded = manager.load_from_entrypoint(
            "api_chaos_agent.services.plugin_framework:BuiltinDataCorruptionPlugin"
        )
        assert loaded is not None
        scenario = _make_scenario(0, ChaosScenarioType.DATA_CORRUPTION)
        result = await manager.execute(
            "data_corruption", scenario, {"corruption_type": "injection"}
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_error_recovery_after_exception(self):
        manager = PluginManager()
        instance = manager._instances["resource_exhaustion"]
        with patch.object(
            instance, "execute", new_callable=AsyncMock, side_effect=RuntimeError("crash")
        ):
            scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
            result = await manager.execute(
                "resource_exhaustion", scenario, {"resource_type": "memory"}
            )
            assert not result.success
            plugin = manager.get("resource_exhaustion")
            assert plugin.status == PluginStatus.ERROR
        manager.enable("resource_exhaustion")
        plugin = manager.get("resource_exhaustion")
        assert plugin.status == PluginStatus.ENABLED
