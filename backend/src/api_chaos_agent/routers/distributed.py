"""API routes for distributed execution engine (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter

from api_chaos_agent.core.exceptions import NotFoundError, RequestError, SchemaError

from api_chaos_agent.core.deps import DistributedEngineDep
from api_chaos_agent.models.distributed import (
    DistributedExecutionPlan,
    Worker,
    WorkerCapabilities,
)

router = APIRouter(prefix="/api/v2/distributed", tags=["distributed"])


@router.post("/workers/register", response_model=Worker)
async def register_worker(
    engine: DistributedEngineDep,
    name: str = "",
    max_concurrency: int = 100,
    region: str = "default",
):
    if not name or not name.strip():
        raise RequestError(detail="Worker name must not be empty")
    caps = WorkerCapabilities(max_concurrency=max_concurrency, region=region)
    return engine.registry.register(name=name, capabilities=caps)


@router.get("/workers", response_model=list[Worker])
async def list_workers(engine: DistributedEngineDep):
    return engine.registry.list_active()


@router.delete("/workers/{worker_id}")
async def deregister_worker(engine: DistributedEngineDep, worker_id: str):
    if not engine.registry.deregister(worker_id):
        raise NotFoundError(detail="Worker not found")
    return {"status": "deregistered"}


@router.post("/workers/{worker_id}/heartbeat")
async def worker_heartbeat(engine: DistributedEngineDep, worker_id: str):
    if not engine.registry.heartbeat(worker_id):
        raise NotFoundError(detail="Worker not found")
    return {"status": "ok"}


@router.get("/plans/{execution_id}", response_model=DistributedExecutionPlan | None)
async def get_execution_plan(engine: DistributedEngineDep, execution_id: str):
    plan = engine.get_plan(execution_id)
    if not plan:
        raise NotFoundError(detail="Execution plan not found")
    return plan
