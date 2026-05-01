"""Execution service — orchestrates scenario execution with store persistence.

Encapsulates the business logic of loading scenarios, configuring the
execution engine, running scenarios, and persisting results. This keeps
the router layer thin and the execution logic testable in isolation.
"""

from __future__ import annotations

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.report import ExecutionConfig
from api_chaos_agent.services.execution_engine import ExecutionEngine
from api_chaos_agent.services.store import store

logger = get_logger(__name__)


class ExecutionService:
    """Orchestrate chaos scenario execution with store persistence."""

    def __init__(self, store: store | None = None) -> None:
        self._store = store

    async def execute_scenarios(
        self,
        scenario_ids: list[str],
        base_url: str,
        concurrency: int = 10,
        timeout_seconds: float = 30.0,
    ) -> dict:
        scenarios = []
        for sid in scenario_ids:
            scenario = await self._store.get_scenario(sid)
            if scenario is None:
                from api_chaos_agent.core.exceptions import NotFoundError
                raise NotFoundError(detail=f"Scenario not found: {sid}")
            scenarios.append(scenario)

        config = ExecutionConfig(
            base_url=base_url,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
        )
        engine = ExecutionEngine(config=config)
        test_result = await engine.execute(scenarios)

        execution_id = await self._store.save_execution(test_result)
        logger.info(
            "scenarios_executed",
            execution_id=execution_id,
            total=len(test_result.results),
            base_url=base_url,
        )
        return {
            "execution_id": execution_id,
            "status": "completed",
            "results": len(test_result.results),
        }
