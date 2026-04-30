"""Unit tests for Phase 2: Distributed Execution Engine."""

import pytest

from api_chaos_agent.models.distributed import WorkerCapabilities, WorkerStatus
from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType, Endpoint
from api_chaos_agent.services.distributed_engine import (
    DistributedExecutionEngine,
    TaskDistributor,
    WorkerRegistry,
)

_DEFAULT_ENDPOINT = Endpoint(path="/api/test", method="GET")


class TestWorkerRegistry:
    def setup_method(self):
        self.registry = WorkerRegistry()

    def test_register_worker(self):
        worker = self.registry.register(name="test-worker")
        assert worker.name == "test-worker"
        assert worker.status == WorkerStatus.IDLE
        assert worker.id in [w.id for w in self.registry.list_active()]

    def test_deregister_worker(self):
        worker = self.registry.register(name="to-remove")
        assert self.registry.deregister(worker.id)
        assert worker not in self.registry.list_active()

    def test_deregister_nonexistent(self):
        assert not self.registry.deregister("nonexistent")

    def test_heartbeat(self):
        worker = self.registry.register(name="hb-worker")
        assert self.registry.heartbeat(worker.id)
        assert not self.registry.heartbeat("nonexistent")

    def test_assign_task(self):
        worker = self.registry.register(name="task-worker")
        assert self.registry.assign_task(worker.id, "task-1")
        assert worker.status == WorkerStatus.RUNNING
        assert worker.current_task_id == "task-1"

    def test_assign_task_to_running_worker_fails(self):
        worker = self.registry.register(name="busy-worker")
        self.registry.assign_task(worker.id, "task-1")
        assert not self.registry.assign_task(worker.id, "task-2")

    def test_complete_task(self):
        worker = self.registry.register(name="comp-worker")
        self.registry.assign_task(worker.id, "task-1")
        self.registry.complete_task(worker.id, success=True)
        assert worker.status == WorkerStatus.IDLE
        assert worker.completed_tasks == 1

    def test_complete_task_failure(self):
        worker = self.registry.register(name="fail-worker")
        self.registry.assign_task(worker.id, "task-1")
        self.registry.complete_task(worker.id, success=False)
        assert worker.failed_tasks == 1


class TestTaskDistributor:
    def setup_method(self):
        self.registry = WorkerRegistry()
        self.distributor = TaskDistributor(self.registry)

    def test_round_robin_distribution(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        scenarios = [
            ChaosScenario(id=f"s{i}", name=f"scenario-{i}", scenario_type=ChaosScenarioType.LATENCY, endpoint=_DEFAULT_ENDPOINT)
            for i in range(4)
        ]
        plan = self.distributor.create_plan("exec-1", scenarios, strategy="round_robin")
        assert plan.total_scenarios == 4
        assert plan.total_workers == 2
        assert len(plan.tasks) == 2
        total_scenarios_in_tasks = sum(len(t.scenario_ids) for t in plan.tasks)
        assert total_scenarios_in_tasks == 4

    def test_no_workers_returns_empty_plan(self):
        scenarios = [ChaosScenario(id="s1", name="test", scenario_type=ChaosScenarioType.LATENCY, endpoint=_DEFAULT_ENDPOINT)]
        plan = self.distributor.create_plan("exec-2", scenarios)
        assert plan.total_workers == 0
        assert len(plan.tasks) == 0

    def test_least_loaded_strategy(self):
        w1 = self.registry.register(name="w1")
        w2 = self.registry.register(name="w2")
        w1.completed_tasks = 100
        w2.completed_tasks = 0
        scenarios = [
            ChaosScenario(id=f"s{i}", name=f"scenario-{i}", scenario_type=ChaosScenarioType.LATENCY, endpoint=_DEFAULT_ENDPOINT)
            for i in range(2)
        ]
        plan = self.distributor.create_plan("exec-3", scenarios, strategy="least_loaded")
        assert plan.strategy == "least_loaded"
        assert len(plan.tasks) > 0
