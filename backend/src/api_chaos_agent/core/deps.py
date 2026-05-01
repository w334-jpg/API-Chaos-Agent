"""FastAPI dependency injection providers.

Centralises the creation and lifecycle of all service instances so that
routers never instantiate services at module-import time.  This eliminates
module-level singletons, makes testing straightforward (just override a
dependency), and guarantees that every component respects the current
``settings`` at runtime.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from api_chaos_agent.services.analytics_service import AnalyticsService
from api_chaos_agent.services.cicd_service import CiCdService
from api_chaos_agent.services.distributed_engine import DistributedExecutionEngine
from api_chaos_agent.services.plugin_framework import PluginManager
from api_chaos_agent.services.store import _StoreProxy, store
from api_chaos_agent.services.tenant_service import TenantService


@lru_cache(maxsize=1)
def get_distributed_engine() -> DistributedExecutionEngine:
    return DistributedExecutionEngine()


@lru_cache(maxsize=1)
def get_plugin_manager() -> PluginManager:
    return PluginManager()


@lru_cache(maxsize=1)
def get_cicd_service() -> CiCdService:
    return CiCdService()


@lru_cache(maxsize=1)
def get_tenant_service() -> TenantService:
    return TenantService()


@lru_cache(maxsize=1)
def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


def get_store() -> _StoreProxy:
    return store


DistributedEngineDep = Annotated[DistributedExecutionEngine, Depends(get_distributed_engine)]
PluginManagerDep = Annotated[PluginManager, Depends(get_plugin_manager)]
CiCdServiceDep = Annotated[CiCdService, Depends(get_cicd_service)]
TenantServiceDep = Annotated[TenantService, Depends(get_tenant_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
StoreDep = Annotated[_StoreProxy, Depends(get_store)]
