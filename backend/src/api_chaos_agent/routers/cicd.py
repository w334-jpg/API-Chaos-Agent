"""API routes for CI/CD pipeline integration (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter

from api_chaos_agent.core.exceptions import NotFoundError, RequestError, SchemaError

from api_chaos_agent.core.deps import CiCdServiceDep
from api_chaos_agent.models.cicd import CiCdProvider, Pipeline, PipelineConfig, PipelineRun

router = APIRouter(prefix="/api/v2/cicd", tags=["cicd"])


@router.post("/pipelines", response_model=Pipeline)
async def create_pipeline(
    service: CiCdServiceDep,
    name: str,
    provider: CiCdProvider,
    config: PipelineConfig,
    tenant_id: str = "",
):
    if not name or not name.strip():
        raise RequestError(detail="Pipeline name must not be empty")
    return service.create_pipeline(name=name, config=config, tenant_id=tenant_id)


@router.get("/pipelines", response_model=list[Pipeline])
async def list_pipelines(service: CiCdServiceDep, tenant_id: str = ""):
    return service.list_pipelines(tenant_id=tenant_id)


@router.get("/pipelines/{pipeline_id}", response_model=Pipeline)
async def get_pipeline(service: CiCdServiceDep, pipeline_id: str):
    pipeline = service.get_pipeline(pipeline_id)
    if not pipeline:
        raise NotFoundError(detail="Pipeline not found")
    return pipeline


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(service: CiCdServiceDep, pipeline_id: str):
    if not service.delete_pipeline(pipeline_id):
        raise NotFoundError(detail="Pipeline not found")
    return {"status": "deleted"}


@router.get("/pipelines/{pipeline_id}/config")
async def generate_pipeline_config(service: CiCdServiceDep, pipeline_id: str):
    config = service.generate_config(pipeline_id)
    if config is None:
        raise NotFoundError(detail="Pipeline not found or provider not supported")
    return {"config": config, "format": "yaml"}


@router.post("/pipelines/{pipeline_id}/trigger", response_model=PipelineRun)
async def trigger_pipeline(service: CiCdServiceDep, pipeline_id: str, commit_sha: str | None = None):
    run = service.trigger_run(pipeline_id, commit_sha=commit_sha)
    if not run:
        raise RequestError(detail="Pipeline not found or disabled")
    return run


@router.get("/pipelines/{pipeline_id}/runs", response_model=list[PipelineRun])
async def list_pipeline_runs(service: CiCdServiceDep, pipeline_id: str):
    return service.get_runs(pipeline_id)
