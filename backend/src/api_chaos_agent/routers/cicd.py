# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""API routes for CI/CD pipeline integration (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api_chaos_agent.models.cicd import CiCdProvider, Pipeline, PipelineConfig, PipelineRun
from api_chaos_agent.services.cicd_service import CiCdService

router = APIRouter(prefix="/api/v2/cicd", tags=["cicd"])

_service = CiCdService()


@router.post("/pipelines", response_model=Pipeline)
async def create_pipeline(name: str, provider: CiCdProvider, config: PipelineConfig, tenant_id: str = ""):
    return _service.create_pipeline(name=name, config=config, tenant_id=tenant_id)


@router.get("/pipelines", response_model=list[Pipeline])
async def list_pipelines(tenant_id: str = ""):
    return _service.list_pipelines(tenant_id=tenant_id)


@router.get("/pipelines/{pipeline_id}", response_model=Pipeline)
async def get_pipeline(pipeline_id: str):
    pipeline = _service.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    if not _service.delete_pipeline(pipeline_id):
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"status": "deleted"}


@router.get("/pipelines/{pipeline_id}/config")
async def generate_pipeline_config(pipeline_id: str):
    config = _service.generate_config(pipeline_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Pipeline not found or provider not supported")
    return {"config": config, "format": "yaml"}


@router.post("/pipelines/{pipeline_id}/trigger", response_model=PipelineRun)
async def trigger_pipeline(pipeline_id: str, commit_sha: str | None = None):
    run = _service.trigger_run(pipeline_id, commit_sha=commit_sha)
    if not run:
        raise HTTPException(status_code=400, detail="Pipeline not found or disabled")
    return run


@router.get("/pipelines/{pipeline_id}/runs", response_model=list[PipelineRun])
async def list_pipeline_runs(pipeline_id: str):
    return _service.get_runs(pipeline_id)
