"""Execution router — manage test executions."""

from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Query

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.deps import StoreDep
from api_chaos_agent.core.exceptions import NotFoundError, RequestError
from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.report import ExecutionConfig, TestResult
from api_chaos_agent.models.scenario import ChaosScenario
from api_chaos_agent.services.execution_engine import ExecutionEngine

router = APIRouter(prefix="/api/executions", tags=["executions"])

_MAX_ID_LEN = 256

_mock_transport: httpx.AsyncBaseTransport | None = None
_mock_transport_enabled: bool = False


def set_mock_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _mock_transport, _mock_transport_enabled
    if not settings.server.debug and os.environ.get("PYTEST_CURRENT_TEST") is None:
        raise RuntimeError("Mock transport can only be set in debug mode or during testing")
    _mock_transport = transport
    _mock_transport_enabled = transport is not None


@router.post("/", response_model=dict)
async def create_execution(
    scenario_ids: Annotated[list[str], Query()],
    base_url: str,
    _user: CurrentUser,
    store: StoreDep,
    concurrency: int = 10,
    timeout_seconds: float = 30.0,
    max_retries: int = 2,
    retry_delay_seconds: float = 1.0,
    serial: bool = False,
) -> dict:
    if not scenario_ids:
        raise RequestError(detail="scenario_ids must be a non-empty list")
    if concurrency < 1:
        raise RequestError(detail="concurrency must be at least 1")
    for sid in scenario_ids:
        if not isinstance(sid, str):
            raise RequestError(detail="Each scenario_id must be a string")
        if len(sid) > _MAX_ID_LEN:
            raise RequestError(detail="scenario_id too long")

    scenarios: list[ChaosScenario] = []
    for sid in scenario_ids:
        scenario = await store.get_scenario(sid)
        if scenario is None:
            raise NotFoundError(detail=f"Scenario not found: {sid}")
        scenarios.append(scenario)

    config = ExecutionConfig(
        base_url=base_url,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
        serial=serial,
    )
    engine = ExecutionEngine(config=config, transport=_mock_transport)
    test_result = await engine.execute(scenarios)

    execution_id = await store.save_execution(test_result)
    return {
        "execution_id": execution_id,
        "total_scenarios": test_result.total_scenarios,
        "completed": test_result.completed_scenarios,
        "failed": test_result.failed_scenarios,
    }


@router.get("/", response_model=dict)
async def list_executions(_user: CurrentUser, store: StoreDep) -> dict:
    executions = await store.list_executions()
    return {
        "executions": [
            {
                "id": eid,
                "started_at": str(e.started_at),
                "total_scenarios": e.total_scenarios,
                "completed": e.completed_scenarios,
                "failed": e.failed_scenarios,
            }
            for eid, e in executions.items()
        ]
    }


@router.get("/{execution_id}", response_model=TestResult)
async def get_execution(execution_id: str, _user: CurrentUser, store: StoreDep) -> TestResult:
    if len(execution_id) > _MAX_ID_LEN:
        raise RequestError(detail="execution_id too long")
    result = await store.get_execution(execution_id)
    if result is None:
        raise NotFoundError(detail="Execution not found")
    return result
