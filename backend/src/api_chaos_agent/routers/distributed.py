# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""API routes for distributed execution engine (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api_chaos_agent.models.distributed import (
    DistributedExecutionPlan,
    Worker,
    WorkerCapabilities,
)
from api_chaos_agent.services.distributed_engine import DistributedExecutionEngine

router = APIRouter(prefix="/api/v2/distributed", tags=["distributed"])

_engine = DistributedExecutionEngine()


@router.post("/workers/register", response_model=Worker)
async def register_worker(name: str = "", max_concurrency: int = 100, region: str = "default"):
    caps = WorkerCapabilities(max_concurrency=max_concurrency, region=region)
    return _engine.registry.register(name=name, capabilities=caps)


@router.get("/workers", response_model=list[Worker])
async def list_workers():
    return _engine.registry.list_active()


@router.delete("/workers/{worker_id}")
async def deregister_worker(worker_id: str):
    if not _engine.registry.deregister(worker_id):
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"status": "deregistered"}


@router.post("/workers/{worker_id}/heartbeat")
async def worker_heartbeat(worker_id: str):
    if not _engine.registry.heartbeat(worker_id):
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"status": "ok"}


@router.get("/plans/{execution_id}", response_model=DistributedExecutionPlan | None)
async def get_execution_plan(execution_id: str):
    plan = _engine.get_plan(execution_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Execution plan not found")
    return plan
