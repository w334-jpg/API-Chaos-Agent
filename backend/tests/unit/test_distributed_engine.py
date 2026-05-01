"""Enhanced TDD tests for Phase 2: Distributed Execution Engine.

Covers: unit tests, functional tests, edge cases, stress tests.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_chaos_agent.models.distributed import (
    DistributedExecutionPlan,
    DistributedTask,
    Worker,
    WorkerCapabilities,
    WorkerStatus,
)
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Endpoint
from api_chaos_agent.services.distributed_engine import (
    DistributedExecutionEngine,
    TaskDistributor,
    WorkerRegistry,
)

_DEFAULT_ENDPOINT = Endpoint(path="/api/test", method="GET")


def _make_scenario(idx: int = 0, stype: ChaosScenarioType = ChaosScenarioType.LATENCY) -> ChaosScenario:
    return ChaosScenario(id=f"s{idx}", name=f"scenario-{idx}", scenario_type=stype, endpoint=_DEFAULT_ENDPOINT)


class TestWorkerRegistryUnit:
    def setup_method(self):
        self.registry = WorkerRegistry()

    def test_register_worker_default_name(self):
        worker = self.registry.register()
        assert worker.name.startswith("worker-")
        assert worker.status == WorkerStatus.IDLE

    def test_register_worker_custom_name(self):
        worker = self.registry.register(name="custom-worker")
        assert worker.name == "custom-worker"

    def test_register_worker_custom_capabilities(self):
        caps = WorkerCapabilities(max_concurrency=200, region="us-east", supported_protocols=["rest", "grpc"])
        worker = self.registry.register(name="cap-worker", capabilities=caps)
        assert worker.capabilities.max_concurrency == 200
        assert worker.capabilities.region == "us-east"
        assert "grpc" in worker.capabilities.supported_protocols

    def test_register_multiple_workers(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        assert w1.id != w2.id
        assert len(self.registry.list_active()) == 2

    def test_deregister_worker(self):
        worker = self.registry.register(name="to-remove")
        assert self.registry.deregister(worker.id)
        assert worker not in self.registry.list_active()

    def test_deregister_nonexistent(self):
        assert not self.registry.deregister("nonexistent")

    def test_deregister_twice(self):
        worker = self.registry.register(name="double-remove")
        assert self.registry.deregister(worker.id)
        assert not self.registry.deregister(worker.id)

    def test_heartbeat_existing_worker(self):
        worker = self.registry.register(name="hb-worker")
        assert self.registry.heartbeat(worker.id)

    def test_heartbeat_nonexistent_worker(self):
        assert not self.registry.heartbeat("nonexistent")

    def test_heartbeat_revives_offline_worker(self):
        worker = self.registry.register(name="revive-worker")
        worker.status = WorkerStatus.OFFLINE
        self.registry.heartbeat(worker.id)
        assert worker.status == WorkerStatus.IDLE

    def test_get_worker(self):
        worker = self.registry.register(name="get-worker")
        found = self.registry.get(worker.id)
        assert found is not None
        assert found.id == worker.id

    def test_get_nonexistent_worker(self):
        assert self.registry.get("nonexistent") is None

    def test_assign_task_to_idle_worker(self):
        worker = self.registry.register(name="task-worker")
        assert self.registry.assign_task(worker.id, "task-1")
        assert worker.status == WorkerStatus.RUNNING
        assert worker.current_task_id == "task-1"

    def test_assign_task_to_running_worker_fails(self):
        worker = self.registry.register(name="busy-worker")
        self.registry.assign_task(worker.id, "task-1")
        assert not self.registry.assign_task(worker.id, "task-2")

    def test_assign_task_to_nonexistent_worker(self):
        assert not self.registry.assign_task("nonexistent", "task-1")

    def test_complete_task_success(self):
        worker = self.registry.register(name="comp-worker")
        self.registry.assign_task(worker.id, "task-1")
        self.registry.complete_task(worker.id, success=True)
        assert worker.status == WorkerStatus.IDLE
        assert worker.completed_tasks == 1
        assert worker.current_task_id is None

    def test_complete_task_failure(self):
        worker = self.registry.register(name="fail-worker")
        self.registry.assign_task(worker.id, "task-1")
        self.registry.complete_task(worker.id, success=False)
        assert worker.status == WorkerStatus.IDLE
        assert worker.failed_tasks == 1
        assert worker.completed_tasks == 0

    def test_complete_task_nonexistent_worker(self):
        assert not self.registry.complete_task("nonexistent")

    def test_complete_task_without_assignment(self):
        worker = self.registry.register(name="free-worker")
        self.registry.complete_task(worker.id, success=True)
        assert worker.completed_tasks == 1
        assert worker.status == WorkerStatus.IDLE

    def test_list_active_excludes_offline(self):
        w1 = self.registry.register(name="active")
        w2 = self.registry.register(name="offline")
        w2.status = WorkerStatus.OFFLINE
        active = self.registry.list_active()
        assert len(active) == 1
        assert active[0].name == "active"

    def test_list_active_empty_registry(self):
        assert self.registry.list_active() == []

    def test_worker_id_is_unique(self):
        workers = [self.registry.register() for _ in range(100)]
        ids = [w.id for w in workers]
        assert len(set(ids)) == 100


class TestWorkerRegistryEdgeCases:
    def setup_method(self):
        self.registry = WorkerRegistry()

    def test_assign_and_complete_multiple_cycles(self):
        worker = self.registry.register(name="cycle-worker")
        for i in range(10):
            self.registry.assign_task(worker.id, f"task-{i}")
            self.registry.complete_task(worker.id, success=True)
        assert worker.completed_tasks == 10
        assert worker.status == WorkerStatus.IDLE

    def test_mixed_success_failure_cycles(self):
        worker = self.registry.register(name="mixed-worker")
        self.registry.assign_task(worker.id, "t1")
        self.registry.complete_task(worker.id, success=True)
        self.registry.assign_task(worker.id, "t2")
        self.registry.complete_task(worker.id, success=False)
        self.registry.assign_task(worker.id, "t3")
        self.registry.complete_task(worker.id, success=True)
        assert worker.completed_tasks == 2
        assert worker.failed_tasks == 1

    def test_heartbeat_does_not_change_running_status(self):
        worker = self.registry.register(name="running-worker")
        self.registry.assign_task(worker.id, "task-1")
        assert worker.status == WorkerStatus.RUNNING
        self.registry.heartbeat(worker.id)
        assert worker.status == WorkerStatus.RUNNING

    def test_worker_capabilities_default_values(self):
        worker = self.registry.register(name="default-caps")
        assert worker.capabilities.max_concurrency == 100
        assert worker.capabilities.region == "default"
        assert worker.capabilities.supported_protocols == ["rest"]
        assert worker.capabilities.labels == {}


class TestTaskDistributorUnit:
    def setup_method(self):
        self.registry = WorkerRegistry()
        self.distributor = TaskDistributor(self.registry)

    def test_round_robin_distribution(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        scenarios = [_make_scenario(i) for i in range(4)]
        plan = self.distributor.create_plan("exec-1", scenarios, strategy="round_robin")
        assert plan.total_scenarios == 4
        assert plan.total_workers == 2
        assert len(plan.tasks) == 2
        total = sum(len(t.scenario_ids) for t in plan.tasks)
        assert total == 4

    def test_round_robin_single_worker(self):
        self.registry.register(name="w1")
        scenarios = [_make_scenario(i) for i in range(3)]
        plan = self.distributor.create_plan("exec-1", scenarios, strategy="round_robin")
        assert len(plan.tasks) == 1
        assert len(plan.tasks[0].scenario_ids) == 3

    def test_round_robin_more_workers_than_scenarios(self):
        for i in range(5):
            self.registry.register(name=f"w{i}")
        scenarios = [_make_scenario(i) for i in range(2)]
        plan = self.distributor.create_plan("exec-1", scenarios, strategy="round_robin")
        assert plan.total_workers == 5
        tasks_with_scenarios = [t for t in plan.tasks if t.scenario_ids]
        assert len(tasks_with_scenarios) == 2

    def test_no_workers_returns_empty_plan(self):
        scenarios = [_make_scenario()]
        plan = self.distributor.create_plan("exec-2", scenarios)
        assert plan.total_workers == 0
        assert len(plan.tasks) == 0

    def test_least_loaded_strategy(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        w1.completed_tasks = 100
        w2.completed_tasks = 0
        scenarios = [_make_scenario(i) for i in range(2)]
        plan = self.distributor.create_plan("exec-3", scenarios, strategy="least_loaded")
        assert plan.strategy == "least_loaded"
        assert len(plan.tasks) > 0

    def test_least_loaded_sorts_by_completed_tasks(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        w3 = self.registry.register(name="w3")
        w1.completed_tasks = 50
        w2.completed_tasks = 10
        w3.completed_tasks = 30
        scenarios = [_make_scenario(i) for i in range(3)]
        plan = self.distributor.create_plan("exec-4", scenarios, strategy="least_loaded")
        assert plan.total_scenarios == 3

    def test_region_aware_strategy(self):
        self.registry.register(name="w-us", capabilities=WorkerCapabilities(region="us-east"))
        self.registry.register(name="w-eu", capabilities=WorkerCapabilities(region="eu-west"))
        scenarios = [_make_scenario(i) for i in range(4)]
        plan = self.distributor.create_plan("exec-5", scenarios, strategy="region_aware")
        assert plan.strategy == "region_aware"
        assert len(plan.tasks) > 0

    def test_region_aware_single_region(self):
        self.registry.register(name="w1", capabilities=WorkerCapabilities(region="us-east"))
        self.registry.register(name="w2", capabilities=WorkerCapabilities(region="us-east"))
        scenarios = [_make_scenario(i) for i in range(4)]
        plan = self.distributor.create_plan("exec-6", scenarios, strategy="region_aware")
        assert len(plan.tasks) > 0
        total = sum(len(t.scenario_ids) for t in plan.tasks)
        assert total == 4

    def test_plan_execution_id_preserved(self):
        self.registry.register(name="w1")
        scenarios = [_make_scenario()]
        plan = self.distributor.create_plan("my-exec-id", scenarios)
        assert plan.execution_id == "my-exec-id"

    def test_plan_strategy_default_round_robin(self):
        self.registry.register(name="w1")
        scenarios = [_make_scenario()]
        plan = self.distributor.create_plan("exec-1", scenarios)
        assert plan.strategy == "round_robin"

    def test_empty_scenarios_with_workers(self):
        self.registry.register(name="w1")
        plan = self.distributor.create_plan("exec-1", [])
        assert plan.total_scenarios == 0
        assert len(plan.tasks) == 0

    def test_task_ids_are_unique(self):
        self.registry.register(name="w1")
        self.registry.register(name="w2")
        scenarios = [_make_scenario(i) for i in range(4)]
        plan = self.distributor.create_plan("exec-1", scenarios)
        task_ids = [t.id for t in plan.tasks]
        assert len(set(task_ids)) == len(task_ids)

    def test_task_worker_ids_reference_valid_workers(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        scenarios = [_make_scenario(i) for i in range(4)]
        plan = self.distributor.create_plan("exec-1", scenarios)
        valid_worker_ids = {w1.id, w2.id}
        for task in plan.tasks:
            assert task.worker_id in valid_worker_ids

    def test_plan_created_at_is_set(self):
        self.registry.register(name="w1")
        scenarios = [_make_scenario()]
        plan = self.distributor.create_plan("exec-1", scenarios)
        assert plan.created_at is not None


class TestDistributedExecutionEngineUnit:
    def setup_method(self):
        self.engine = DistributedExecutionEngine()

    def test_engine_has_registry(self):
        assert self.engine.registry is not None

    def test_register_worker_via_engine(self):
        worker = self.engine.registry.register(name="engine-worker")
        assert worker.name == "engine-worker"

    def test_get_plan_nonexistent(self):
        assert self.engine.get_plan("nonexistent") is None

    @pytest.mark.asyncio
    async def test_execute_distributed_no_workers(self):
        scenarios = [_make_scenario()]
        from api_chaos_agent.models.report import ExecutionConfig
        config = ExecutionConfig(base_url="http://test.local")
        results = await self.engine.execute_distributed("exec-1", scenarios, config)
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_distributed_with_mocked_engine(self):
        self.engine.registry.register(name="w1")
        scenarios = [_make_scenario(i) for i in range(2)]
        from api_chaos_agent.models.report import ExecutionConfig, ScenarioResult
        config = ExecutionConfig(base_url="http://test.local")
        mock_result = ScenarioResult(scenario_id="s0", scenario_name="scenario-0", scenario_type="latency", success=True)
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[mock_result]))
            MockEngine.return_value = mock_instance
            results = await self.engine.execute_distributed("exec-mock", scenarios, config)
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_execute_distributed_stores_plan(self):
        self.engine.registry.register(name="w1")
        scenarios = [_make_scenario()]
        from api_chaos_agent.models.report import ExecutionConfig
        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            await self.engine.execute_distributed("exec-plan", scenarios, config)
            plan = self.engine.get_plan("exec-plan")
            assert plan is not None
            assert plan.execution_id == "exec-plan"

    @pytest.mark.asyncio
    async def test_execute_distributed_worker_completes(self):
        worker = self.engine.registry.register(name="w1")
        scenarios = [_make_scenario()]
        from api_chaos_agent.models.report import ExecutionConfig
        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            await self.engine.execute_distributed("exec-comp", scenarios, config)
            assert worker.completed_tasks == 1

    @pytest.mark.asyncio
    async def test_execute_distributed_worker_fails(self):
        worker = self.engine.registry.register(name="w1")
        scenarios = [_make_scenario()]
        from api_chaos_agent.models.report import ExecutionConfig
        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(side_effect=RuntimeError("boom"))
            MockEngine.return_value = mock_instance
            results = await self.engine.execute_distributed("exec-fail", scenarios, config)
            assert worker.failed_tasks == 1

    @pytest.mark.asyncio
    async def test_execute_distributed_multiple_workers(self):
        self.engine.registry.register(name="w1")
        self.engine.registry.register(name="w2")
        scenarios = [_make_scenario(i) for i in range(4)]
        from api_chaos_agent.models.report import ExecutionConfig
        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            results = await self.engine.execute_distributed("exec-multi", scenarios, config)
            plan = self.engine.get_plan("exec-multi")
            assert plan.total_workers == 2


class TestDistributedEngineStress:
    def test_register_many_workers(self):
        registry = WorkerRegistry()
        workers = [registry.register(name=f"w{i}") for i in range(200)]
        assert len(registry.list_active()) == 200

    def test_distribute_many_scenarios(self):
        registry = WorkerRegistry()
        for i in range(10):
            registry.register(name=f"w{i}")
        distributor = TaskDistributor(registry)
        scenarios = [_make_scenario(i) for i in range(500)]
        plan = distributor.create_plan("stress-1", scenarios, strategy="round_robin")
        assert plan.total_scenarios == 500
        total = sum(len(t.scenario_ids) for t in plan.tasks)
        assert total == 500

    def test_distribute_performance_under_1_second(self):
        registry = WorkerRegistry()
        for i in range(50):
            registry.register(name=f"w{i}")
        distributor = TaskDistributor(registry)
        scenarios = [_make_scenario(i) for i in range(1000)]
        start = time.monotonic()
        plan = distributor.create_plan("perf-1", scenarios, strategy="round_robin")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Distribution took {elapsed:.3f}s, expected < 1.0s"

    def test_assign_complete_many_cycles(self):
        registry = WorkerRegistry()
        worker = registry.register(name="cycle-worker")
        start = time.monotonic()
        for i in range(1000):
            registry.assign_task(worker.id, f"task-{i}")
            registry.complete_task(worker.id, success=True)
        elapsed = time.monotonic() - start
        assert worker.completed_tasks == 1000
        assert elapsed < 2.0, f"1000 cycles took {elapsed:.3f}s"

    def test_concurrent_worker_registrations(self):
        registry = WorkerRegistry()
        workers = []
        for i in range(100):
            w = registry.register(name=f"w{i}")
            workers.append(w)
        active = registry.list_active()
        assert len(active) == 100

    @pytest.mark.asyncio
    async def test_execute_distributed_many_workers_mocked(self):
        engine = DistributedExecutionEngine()
        for i in range(20):
            engine.registry.register(name=f"w{i}")
        scenarios = [_make_scenario(i) for i in range(40)]
        from api_chaos_agent.models.report import ExecutionConfig
        config = ExecutionConfig(base_url="http://test.local")
        with patch("api_chaos_agent.services.execution_engine.ExecutionEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=MagicMock(results=[]))
            MockEngine.return_value = mock_instance
            start = time.monotonic()
            results = await engine.execute_distributed("stress-exec", scenarios, config)
            elapsed = time.monotonic() - start
            assert elapsed < 5.0, f"Distributed execution took {elapsed:.3f}s"


class TestDistributedEngineFunctional:
    def test_full_workflow_register_distribute_execute(self):
        registry = WorkerRegistry()
        distributor = TaskDistributor(registry)
        w1 = registry.register(name="w1", capabilities=WorkerCapabilities(region="us-east"))
        w2 = registry.register(name="w2", capabilities=WorkerCapabilities(region="eu-west"))
        scenarios = [_make_scenario(i, stype) for i, stype in enumerate([
            ChaosScenarioType.LATENCY,
            ChaosScenarioType.ERROR_STATUS,
            ChaosScenarioType.NETWORK_PARTITION,
            ChaosScenarioType.LATENCY,
        ])]
        plan = distributor.create_plan("func-1", scenarios, strategy="round_robin")
        assert plan.total_scenarios == 4
        assert plan.total_workers == 2
        for task in plan.tasks:
            assert task.worker_id in (w1.id, w2.id)
            assert len(task.scenario_ids) > 0

    def test_region_aware_distribution_with_multiple_regions(self):
        registry = WorkerRegistry()
        distributor = TaskDistributor(registry)
        us_workers = [registry.register(name=f"us-{i}", capabilities=WorkerCapabilities(region="us-east")) for i in range(3)]
        eu_workers = [registry.register(name=f"eu-{i}", capabilities=WorkerCapabilities(region="eu-west")) for i in range(2)]
        scenarios = [_make_scenario(i) for i in range(10)]
        plan = distributor.create_plan("func-region", scenarios, strategy="region_aware")
        assert plan.strategy == "region_aware"
        assert len(plan.tasks) > 0
        total = sum(len(t.scenario_ids) for t in plan.tasks)
        assert total == 10

    def test_plan_serialization(self):
        registry = WorkerRegistry()
        distributor = TaskDistributor(registry)
        registry.register(name="w1")
        scenarios = [_make_scenario()]
        plan = distributor.create_plan("serial-1", scenarios)
        data = plan.model_dump()
        assert data["execution_id"] == "serial-1"
        assert data["strategy"] == "round_robin"

    def test_plan_roundtrip(self):
        registry = WorkerRegistry()
        distributor = TaskDistributor(registry)
        registry.register(name="w1")
        scenarios = [_make_scenario()]
        plan = distributor.create_plan("rt-1", scenarios)
        data = plan.model_dump()
        restored = DistributedExecutionPlan(**data)
        assert restored.execution_id == plan.execution_id
        assert restored.total_scenarios == plan.total_scenarios

    def test_worker_task_lifecycle(self):
        registry = WorkerRegistry()
        worker = registry.register(name="lifecycle-worker")
        assert worker.status == WorkerStatus.IDLE
        assert worker.completed_tasks == 0
        assert worker.failed_tasks == 0
        registry.assign_task(worker.id, "task-1")
        assert worker.status == WorkerStatus.RUNNING
        assert worker.current_task_id == "task-1"
        registry.heartbeat(worker.id)
        assert worker.status == WorkerStatus.RUNNING
        registry.complete_task(worker.id, success=True)
        assert worker.status == WorkerStatus.IDLE
        assert worker.completed_tasks == 1
        assert worker.current_task_id is None
