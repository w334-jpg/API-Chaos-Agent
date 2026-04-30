"""Unit tests for Phase 2: Fault Plugin Framework."""

import pytest

from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Endpoint
from api_chaos_agent.services.plugin_framework import PluginManager

_DEFAULT_ENDPOINT = Endpoint(path="/api/test", method="GET")


class TestPluginManager:
    def setup_method(self):
        self.manager = PluginManager()

    def test_builtin_plugins_loaded(self):
        plugins = self.manager.list_plugins()
        assert len(plugins) >= 4
        names = [p.manifest.name for p in plugins]
        assert "resource_exhaustion" in names
        assert "data_corruption" in names
        assert "dependency_failure" in names
        assert "network_partition" in names

    def test_get_plugin(self):
        plugin = self.manager.get("resource_exhaustion")
        assert plugin is not None
        assert plugin.manifest.name == "resource_exhaustion"

    def test_get_nonexistent_plugin(self):
        assert self.manager.get("nonexistent") is None

    def test_enable_disable_plugin(self):
        assert self.manager.disable("resource_exhaustion")
        plugin = self.manager.get("resource_exhaustion")
        assert plugin.status.value == "disabled"
        assert self.manager.enable("resource_exhaustion")
        assert plugin.status.value == "enabled"

    def test_enable_nonexistent(self):
        assert not self.manager.enable("nonexistent")

    @pytest.mark.asyncio
    async def test_execute_resource_exhaustion_plugin(self):
        scenario = ChaosScenario(id="s1", name="test", scenario_type=ChaosScenarioType.RESOURCE_EXHAUSTION, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("resource_exhaustion", scenario, {"resource_type": "memory", "intensity": "high"})
        assert result.success
        assert result.output["injected"]
        assert result.output["resource_type"] == "memory"

    @pytest.mark.asyncio
    async def test_execute_data_corruption_plugin(self):
        scenario = ChaosScenario(id="s2", name="test", scenario_type=ChaosScenarioType.DATA_CORRUPTION, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("data_corruption", scenario, {"corruption_type": "truncation"})
        assert result.success
        assert result.output["corruption_type"] == "truncation"

    @pytest.mark.asyncio
    async def test_execute_dependency_failure_plugin(self):
        scenario = ChaosScenario(id="s3", name="test", scenario_type=ChaosScenarioType.DEPENDENCY_FAILURE, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("dependency_failure", scenario, {"failure_type": "timeout"})
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_network_partition_plugin(self):
        scenario = ChaosScenario(id="s4", name="test", scenario_type=ChaosScenarioType.NETWORK_PARTITION, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("network_partition", scenario, {"partition_type": "packet_loss"})
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_disabled_plugin_fails(self):
        self.manager.disable("resource_exhaustion")
        scenario = ChaosScenario(id="s5", name="test", scenario_type=ChaosScenarioType.RESOURCE_EXHAUSTION, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        assert not result.success
        assert "not enabled" in result.error

    @pytest.mark.asyncio
    async def test_execute_nonexistent_plugin(self):
        scenario = ChaosScenario(id="s6", name="test", scenario_type=ChaosScenarioType.CUSTOM_PLUGIN, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("nonexistent", scenario, {})
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_invalid_config(self):
        scenario = ChaosScenario(id="s7", name="test", scenario_type=ChaosScenarioType.RESOURCE_EXHAUSTION, endpoint=_DEFAULT_ENDPOINT)
        result = await self.manager.execute("resource_exhaustion", scenario, {"invalid_key": "value"})
        assert not result.success
        assert "validation failed" in result.error.lower()

    def test_list_plugins_by_status(self):
        from api_chaos_agent.models.plugin import PluginStatus
        enabled = self.manager.list_plugins(status=PluginStatus.ENABLED)
        assert len(enabled) >= 4
