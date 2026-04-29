"""Scenarios router — generate and manage chaos test scenarios."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException

from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.scenario import ChaosScenario
from api_chaos_agent.services.llm_router import LLMRouter
from api_chaos_agent.services.scenario_generator import ScenarioGenerator
from api_chaos_agent.services.store import store

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

_MAX_ID_LEN = 256


@router.post("/generate/{schema_id}", response_model=dict)
async def generate_scenarios(schema_id: str, _user: CurrentUser) -> dict:
    if len(schema_id) > _MAX_ID_LEN:
        raise HTTPException(status_code=400, detail="schema_id too long")

    spec = await store.get_schema(schema_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Schema not found")

    llm_router = LLMRouter()
    generator = ScenarioGenerator(llm_router=llm_router)
    scenarios = await generator.generate(spec)

    scenario_ids: list[str] = []
    for scenario in scenarios:
        sid = await store.save_scenario(scenario)
        scenario_ids.append(sid)

    return {
        "schema_id": schema_id,
        "scenarios_generated": len(scenario_ids),
        "scenario_ids": scenario_ids,
    }


@router.get("/", response_model=dict)
async def list_scenarios(_user: CurrentUser) -> dict:
    scenarios = await store.list_scenarios()
    return {
        "scenarios": [
            {
                "id": sid,
                "name": s.name,
                "type": s.scenario_type.value,
                "severity": s.severity.value,
                "endpoint": f"{s.endpoint.method.value} {s.endpoint.path}",
            }
            for sid, s in scenarios.items()
        ]
    }


@router.get("/{scenario_id}", response_model=ChaosScenario)
async def get_scenario(scenario_id: str, _user: CurrentUser) -> ChaosScenario:
    if len(scenario_id) > _MAX_ID_LEN:
        raise HTTPException(status_code=400, detail="scenario_id too long")
    scenario = await store.get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@router.post("/execute", response_model=dict)
async def execute_scenarios(
    scenario_ids: list[str],
    base_url: str,
    _user: CurrentUser,
    concurrency: int = 10,
    timeout_seconds: float = 30.0,
) -> dict:
    if not scenario_ids:
        raise HTTPException(status_code=400, detail="scenario_ids must be a non-empty list")

    for sid in scenario_ids:
        if not isinstance(sid, str):
            raise HTTPException(status_code=400, detail="Each scenario_id must be a string")
        if len(sid) > _MAX_ID_LEN:
            raise HTTPException(status_code=400, detail="scenario_id too long")

    scenarios: list[ChaosScenario] = []
    for sid in scenario_ids:
        scenario = await store.get_scenario(sid)
        if scenario is None:
            raise HTTPException(status_code=404, detail=f"Scenario not found: {sid}")
        scenarios.append(scenario)

    from api_chaos_agent.models.report import ExecutionConfig
    from api_chaos_agent.services.execution_engine import ExecutionEngine

    config = ExecutionConfig(
        base_url=base_url,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
    )
    engine = ExecutionEngine(config=config)
    test_result = await engine.execute(scenarios)

    execution_id = await store.save_execution(test_result)
    return {"execution_id": execution_id, "status": "completed", "results": len(test_result.results)}
