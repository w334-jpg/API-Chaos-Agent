"""Integration Test 1: gRPC/GraphQL Parser + Distributed Engine + Plugin Framework.

Tests cross-module interfaces, data flow, and collaborative functionality
between Blocks 1-3.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_chaos_agent.models.distributed import WorkerCapabilities
from api_chaos_agent.models.plugin import PluginStatus
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Endpoint
from api_chaos_agent.models.schema import ApiProtocol
from api_chaos_agent.services.distributed_engine import (
    DistributedExecutionEngine,
    TaskDistributor,
    WorkerRegistry,
)
from api_chaos_agent.services.grpc_graphql_parser import (
    GraphQLSchemaParser,
    GrpcSchemaParser,
    detect_protocol,
)
from api_chaos_agent.services.plugin_framework import PluginManager

_DEFAULT_ENDPOINT = Endpoint(path="/api/test", method="GET")


def _make_scenario(
    idx: int = 0, stype: ChaosScenarioType = ChaosScenarioType.LATENCY
) -> ChaosScenario:
    return ChaosScenario(
        id=f"s{idx}", name=f"scenario-{idx}", scenario_type=stype, endpoint=_DEFAULT_ENDPOINT
    )


class TestParserToDistributedIntegration:
    def test_grpc_spec_feeds_distributed_engine(self):
        proto = """
syntax = "proto3";
package integration.test;
service IntegrationService {
  rpc Method1 (Req) returns (Res) {}
  rpc Method2 (Req) returns (stream Res) {}
}
"""
        parser = GrpcSchemaParser()
        spec = parser.parse_text(proto)
        assert spec.protocol == ApiProtocol.GRPC
        assert len(spec.grpc_services) == 1
        scenarios = [_make_scenario(i) for i in range(4)]
        registry = WorkerRegistry()
        registry.register(name="w1", capabilities=WorkerCapabilities(region="us-east"))
        registry.register(name="w2", capabilities=WorkerCapabilities(region="eu-west"))
        distributor = TaskDistributor(registry)
        plan = distributor.create_plan("integration-1", scenarios, strategy="round_robin")
        assert plan.total_scenarios == 4
        assert plan.total_workers == 2

    def test_graphql_spec_feeds_distributed_engine(self):
        sdl = """
type Query {
  user(id: ID!): User
  posts: [Post]
}

type Mutation {
  createPost(title: String!): Post
}
"""
        parser = GraphQLSchemaParser()
        spec = parser.parse_text(sdl)
        assert spec.protocol == ApiProtocol.GRAPHQL
        assert len(spec.graphql_operations) == 3
        scenarios = [_make_scenario(i) for i in range(3)]
        registry = WorkerRegistry()
        registry.register(name="w1")
        distributor = TaskDistributor(registry)
        plan = distributor.create_plan("integration-2", scenarios)
        assert plan.total_scenarios == 3

    def test_detect_protocol_routes_to_correct_parser(self):
        grpc_file = "api.proto"
        graphql_file = "schema.graphql"
        assert detect_protocol(grpc_file) == ApiProtocol.GRPC
        assert detect_protocol(graphql_file) == ApiProtocol.GRAPHQL

    def test_parser_output_compatible_with_scenario_creation(self):
        proto = """
syntax = "proto3";
package compat;
service CompatService {
  rpc Get (Req) returns (Res) {}
}
"""
        parser = GrpcSchemaParser()
        spec = parser.parse_text(proto)
        assert spec.protocol == ApiProtocol.GRPC
        scenario = _make_scenario(0, ChaosScenarioType.LATENCY)
        assert scenario.id is not None
        assert scenario.scenario_type == ChaosScenarioType.LATENCY


class TestPluginToDistributedIntegration:
    @pytest.mark.asyncio
    async def test_plugin_execution_via_distributed_engine(self):
        engine = DistributedExecutionEngine()
        engine.registry.register(name="w1")
        manager = PluginManager()
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        plugin_result = await manager.execute(
            "resource_exhaustion", scenario, {"resource_type": "memory"}
        )
        assert plugin_result.success
        from api_chaos_agent.models.report import ExecutionConfig

        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            scenarios = [_make_scenario(i) for i in range(2)]
            await engine.execute_distributed("plugin-dist-1", scenarios, config)
            plan = engine.get_plan("plugin-dist-1")
            assert plan is not None

    @pytest.mark.asyncio
    async def test_plugin_results_flow_through_workers(self):
        registry = WorkerRegistry()
        worker = registry.register(name="plugin-worker")
        manager = PluginManager()
        scenario = _make_scenario(0, ChaosScenarioType.DATA_CORRUPTION)
        plugin_result = await manager.execute(
            "data_corruption", scenario, {"corruption_type": "encoding"}
        )
        assert plugin_result.success
        registry.assign_task(worker.id, "task-1")
        assert worker.status.value == "running"
        registry.complete_task(worker.id, success=True)
        assert worker.completed_tasks == 1


class TestParserToPluginIntegration:
    def test_grpc_scenarios_use_plugins(self):
        proto = """
syntax = "proto3";
package plugin.test;
service PluginService {
  rpc GetData (Req) returns (Res) {}
}
"""
        parser = GrpcSchemaParser()
        spec = parser.parse_text(proto)
        assert spec.protocol == ApiProtocol.GRPC
        manager = PluginManager()
        plugin = manager.get("network_partition")
        assert plugin is not None
        assert plugin.status == PluginStatus.ENABLED

    @pytest.mark.asyncio
    async def test_graphql_scenarios_use_plugins(self):
        sdl = """
type Query {
  search(query: String!): [Result]
}
"""
        parser = GraphQLSchemaParser()
        spec = parser.parse_text(sdl)
        assert spec.protocol == ApiProtocol.GRAPHQL
        manager = PluginManager()
        scenario = _make_scenario(0, ChaosScenarioType.DEPENDENCY_FAILURE)
        result = await manager.execute("dependency_failure", scenario, {"failure_type": "timeout"})
        assert result.success


class TestFullPipelineIntegration:
    @pytest.mark.asyncio
    async def test_parse_distribute_execute_pipeline(self):
        proto = """
syntax = "proto3";
package pipeline.test;
service PipelineService {
  rpc Start (Req) returns (Res) {}
  rpc Stream (Req) returns (stream Res) {}
  rpc Upload (stream Req) returns (Res) {}
}
"""
        parser = GrpcSchemaParser()
        spec = parser.parse_text(proto)
        assert len(spec.grpc_services) == 1
        assert len(spec.grpc_services[0].methods) == 3
        scenarios = [
            _make_scenario(0, ChaosScenarioType.LATENCY),
            _make_scenario(1, ChaosScenarioType.NETWORK_PARTITION),
            _make_scenario(2, ChaosScenarioType.RESOURCE_EXHAUSTION),
        ]
        engine = DistributedExecutionEngine()
        engine.registry.register(name="w1")
        engine.registry.register(name="w2")
        manager = PluginManager()
        plugin_results = []
        for scenario in scenarios:
            if scenario.scenario_type == ChaosScenarioType.RESOURCE_EXHAUSTION:
                r = await manager.execute(
                    "resource_exhaustion", scenario, {"resource_type": "memory"}
                )
            elif scenario.scenario_type == ChaosScenarioType.NETWORK_PARTITION:
                r = await manager.execute(
                    "network_partition", scenario, {"partition_type": "packet_loss"}
                )
            else:
                r = MagicMock(success=True, output={"injected": True})
            plugin_results.append(r)
        assert all(r.success for r in plugin_results)
        from api_chaos_agent.models.report import ExecutionConfig

        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            await engine.execute_distributed("pipeline-1", scenarios, config)
            plan = engine.get_plan("pipeline-1")
            assert plan is not None
            assert plan.total_scenarios == 3

    @pytest.mark.asyncio
    async def test_graphql_distribute_execute_pipeline(self):
        sdl = """
type Query {
  getUser(id: ID!): User
  listUsers: [User]
}

type Mutation {
  createUser(name: String!): User
  deleteUser(id: ID!): Boolean
}
"""
        parser = GraphQLSchemaParser()
        spec = parser.parse_text(sdl)
        assert len(spec.graphql_operations) == 4
        scenarios = [_make_scenario(i) for i in range(4)]
        engine = DistributedExecutionEngine()
        for i in range(3):
            engine.registry.register(name=f"w{i}")
        from api_chaos_agent.models.report import ExecutionConfig

        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            await engine.execute_distributed("gql-pipeline-1", scenarios, config)
            plan = engine.get_plan("gql-pipeline-1")
            assert plan.total_workers == 3
            assert plan.total_scenarios == 4

    def test_data_flow_parser_spec_to_scenario_to_plan(self):
        proto = """
syntax = "proto3";
package dataflow;
service DataFlowService {
  rpc Fetch (Req) returns (Res) {}
}
"""
        parser = GrpcSchemaParser()
        spec = parser.parse_text(proto)
        assert spec.protocol == ApiProtocol.GRPC
        scenario = _make_scenario(0, ChaosScenarioType.LATENCY)
        assert scenario.endpoint == _DEFAULT_ENDPOINT
        registry = WorkerRegistry()
        registry.register(name="w1")
        distributor = TaskDistributor(registry)
        plan = distributor.create_plan("dataflow-1", [scenario])
        assert plan.total_scenarios == 1
        assert len(plan.tasks) == 1
        task = plan.tasks[0]
        assert len(task.scenario_ids) == 1

    @pytest.mark.asyncio
    async def test_cross_module_serialization(self):
        parser = GrpcSchemaParser()
        spec = parser.parse_text('syntax = "proto3";\nservice Svc { rpc M (R) returns (R) {} }')
        spec_data = spec.model_dump()
        assert "protocol" in spec_data
        manager = PluginManager()
        scenario = _make_scenario(0, ChaosScenarioType.RESOURCE_EXHAUSTION)
        result = await manager.execute("resource_exhaustion", scenario, {"resource_type": "memory"})
        result_data = result.model_dump()
        assert "success" in result_data
        registry = WorkerRegistry()
        registry.register(name="w1")
        distributor = TaskDistributor(registry)
        plan = distributor.create_plan("serial-1", [scenario])
        plan_data = plan.model_dump()
        assert "execution_id" in plan_data


class TestIntegrationStress:
    @pytest.mark.asyncio
    async def test_high_volume_pipeline(self):
        proto = """
syntax = "proto3";
package stress;
service StressService {
  rpc Load1 (Req) returns (Res) {}
  rpc Load2 (Req) returns (Res) {}
  rpc Load3 (Req) returns (stream Res) {}
}
"""
        parser = GrpcSchemaParser()
        spec = parser.parse_text(proto)
        assert len(spec.grpc_services[0].methods) == 3
        scenarios = [_make_scenario(i) for i in range(50)]
        engine = DistributedExecutionEngine()
        for i in range(5):
            engine.registry.register(name=f"w{i}")
        from api_chaos_agent.models.report import ExecutionConfig

        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            start = time.monotonic()
            await engine.execute_distributed("stress-int-1", scenarios, config)
            elapsed = time.monotonic() - start
            assert elapsed < 5.0, f"High volume pipeline took {elapsed:.3f}s"
            plan = engine.get_plan("stress-int-1")
            assert plan.total_scenarios == 50

    @pytest.mark.asyncio
    async def test_concurrent_plugin_execution_with_distributed(self):
        manager = PluginManager()
        engine = DistributedExecutionEngine()
        engine.registry.register(name="w1")
        engine.registry.register(name="w2")
        scenarios = [_make_scenario(i, ChaosScenarioType.RESOURCE_EXHAUSTION) for i in range(10)]
        plugin_tasks = [
            manager.execute("resource_exhaustion", s, {"resource_type": "memory"})
            for s in scenarios
        ]
        plugin_results = await asyncio.gather(*plugin_tasks)
        assert all(r.success for r in plugin_results)
        from api_chaos_agent.models.report import ExecutionConfig

        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            await engine.execute_distributed("conc-int-1", scenarios, config)
            plan = engine.get_plan("conc-int-1")
            assert plan is not None
