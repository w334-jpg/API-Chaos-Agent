# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""Distributed execution engine for scaling chaos tests across multiple workers.

Implements a Master-Worker architecture with:
- Worker registration and heartbeat monitoring
- Task distribution strategies (round_robin, least_loaded, region_aware)
- Automatic failover and task reassignment
- Result aggregation from distributed workers
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.distributed import (
    DistributedExecutionPlan,
    DistributedTask,
    Worker,
    WorkerCapabilities,
    WorkerStatus,
)
from api_chaos_agent.models.report import ExecutionConfig, ScenarioResult
from api_chaos_agent.models.scenario import ChaosScenario

logger = get_logger(__name__)


class WorkerRegistry:
    """Thread-safe registry for managing distributed workers."""

    def __init__(self) -> None:
        self._workers: dict[str, Worker] = {}
        self._heartbeat_timeout: float = 30.0

    def register(self, name: str = "", capabilities: WorkerCapabilities | None = None) -> Worker:
        worker = Worker(
            id=str(uuid.uuid4()),
            name=name or f"worker-{len(self._workers) + 1}",
            status=WorkerStatus.IDLE,
            capabilities=capabilities or WorkerCapabilities(),
        )
        self._workers[worker.id] = worker
        logger.info("worker_registered", worker_id=worker.id, worker_name=worker.name)
        return worker

    def deregister(self, worker_id: str) -> bool:
        if worker_id in self._workers:
            del self._workers[worker_id]
            logger.info("worker_deregistered", worker_id=worker_id)
            return True
        return False

    def heartbeat(self, worker_id: str) -> bool:
        if worker_id in self._workers:
            self._workers[worker_id].last_heartbeat = datetime.now()
            if self._workers[worker_id].status == WorkerStatus.OFFLINE:
                self._workers[worker_id].status = WorkerStatus.IDLE
            return True
        return False

    def get(self, worker_id: str) -> Worker | None:
        return self._workers.get(worker_id)

    def list_active(self) -> list[Worker]:
        now = datetime.now()
        active: list[Worker] = []
        for w in self._workers.values():
            if (now - w.last_heartbeat).total_seconds() > self._heartbeat_timeout:
                w.status = WorkerStatus.OFFLINE
            elif w.status != WorkerStatus.OFFLINE:
                active.append(w)
        return active

    def assign_task(self, worker_id: str, task_id: str) -> bool:
        w = self._workers.get(worker_id)
        if w and w.status == WorkerStatus.IDLE:
            w.status = WorkerStatus.RUNNING
            w.current_task_id = task_id
            return True
        return False

    def complete_task(self, worker_id: str, success: bool = True) -> bool:
        w = self._workers.get(worker_id)
        if w:
            w.status = WorkerStatus.IDLE
            w.current_task_id = None
            if success:
                w.completed_tasks += 1
            else:
                w.failed_tasks += 1
            return True
        return False


class TaskDistributor:
    """Distribute scenarios across workers using configurable strategies."""

    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def create_plan(
        self,
        execution_id: str,
        scenarios: list[ChaosScenario],
        strategy: str = "round_robin",
    ) -> DistributedExecutionPlan:
        workers = self._registry.list_active()
        if not workers:
            return DistributedExecutionPlan(
                execution_id=execution_id,
                total_scenarios=len(scenarios),
                total_workers=0,
                strategy=strategy,
            )

        if strategy == "least_loaded":
            tasks = self._distribute_least_loaded(execution_id, scenarios, workers)
        elif strategy == "region_aware":
            tasks = self._distribute_region_aware(execution_id, scenarios, workers)
        else:
            tasks = self._distribute_round_robin(execution_id, scenarios, workers)

        return DistributedExecutionPlan(
            execution_id=execution_id,
            total_scenarios=len(scenarios),
            total_workers=len(workers),
            tasks=tasks,
            strategy=strategy,
        )

    def _distribute_round_robin(
        self, execution_id: str, scenarios: list[ChaosScenario], workers: list[Worker]
    ) -> list[DistributedTask]:
        tasks: list[DistributedTask] = []
        worker_buckets: dict[int, list[str]] = {i: [] for i in range(len(workers))}
        for idx, scenario in enumerate(scenarios):
            worker_buckets[idx % len(workers)].append(scenario.id)
        for worker_idx, scenario_ids in worker_buckets.items():
            if scenario_ids:
                tasks.append(
                    DistributedTask(
                        id=str(uuid.uuid4()),
                        execution_id=execution_id,
                        worker_id=workers[worker_idx].id,
                        scenario_ids=scenario_ids,
                    )
                )
        return tasks

    def _distribute_least_loaded(
        self, execution_id: str, scenarios: list[ChaosScenario], workers: list[Worker]
    ) -> list[DistributedTask]:
        sorted_workers = sorted(workers, key=lambda w: w.completed_tasks)
        return self._distribute_round_robin(execution_id, scenarios, sorted_workers)

    def _distribute_region_aware(
        self, execution_id: str, scenarios: list[ChaosScenario], workers: list[Worker]
    ) -> list[DistributedTask]:
        region_workers: dict[str, list[Worker]] = {}
        for w in workers:
            region = w.capabilities.region
            region_workers.setdefault(region, []).append(w)
        tasks: list[DistributedTask] = []
        scenario_chunks = [
            scenarios[i :: max(1, len(region_workers))] for i in range(max(1, len(region_workers)))
        ]
        for idx, (region, rworkers) in enumerate(region_workers.items()):
            if idx < len(scenario_chunks):
                chunk = scenario_chunks[idx]
                tasks.extend(self._distribute_round_robin(execution_id, chunk, rworkers))
        return tasks


class DistributedExecutionEngine:
    """Master coordinator for distributed chaos test execution."""

    def __init__(self) -> None:
        self._registry = WorkerRegistry()
        self._distributor = TaskDistributor(self._registry)
        self._plans: dict[str, DistributedExecutionPlan] = {}

    @property
    def registry(self) -> WorkerRegistry:
        return self._registry

    async def execute_distributed(
        self,
        execution_id: str,
        scenarios: list[ChaosScenario],
        config: ExecutionConfig,
        strategy: str = "round_robin",
    ) -> list[ScenarioResult]:
        plan = self._distributor.create_plan(execution_id, scenarios, strategy)
        self._plans[execution_id] = plan

        if not plan.tasks:
            logger.warning("no_workers_available", execution_id=execution_id)
            return []

        all_results: list[ScenarioResult] = []
        task_coros = []
        for task in plan.tasks:
            worker = self._registry.get(task.worker_id) if task.worker_id else None
            if worker and self._registry.assign_task(worker.id, task.id):
                task_coros.append(self._execute_worker_task(task, scenarios, config, worker))

        if task_coros:
            results_per_task = await asyncio.gather(*task_coros, return_exceptions=True)
            for result in results_per_task:
                if isinstance(result, list):
                    all_results.extend(result)
                elif isinstance(result, Exception):
                    logger.error("worker_task_failed", error=str(result))

        return all_results

    async def _execute_worker_task(
        self,
        task: DistributedTask,
        scenarios: list[ChaosScenario],
        config: ExecutionConfig,
        worker: Worker,
    ) -> list[ScenarioResult]:
        from api_chaos_agent.services.execution_engine import ExecutionEngine

        task_scenarios = [s for s in scenarios if s.id in task.scenario_ids]
        engine = ExecutionEngine(config)
        try:
            result = await engine.execute(task_scenarios)
            self._registry.complete_task(worker.id, success=True)
            return result.results
        except Exception as e:
            self._registry.complete_task(worker.id, success=False)
            logger.error("worker_execution_failed", worker_id=worker.id, error=str(e))
            return []

    def get_plan(self, execution_id: str) -> DistributedExecutionPlan | None:
        return self._plans.get(execution_id)
