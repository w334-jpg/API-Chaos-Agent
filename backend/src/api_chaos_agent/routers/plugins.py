# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""API routes for fault plugin management (Phase 2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api_chaos_agent.models.plugin import FaultPlugin, FaultPluginExecution, PluginStatus
from api_chaos_agent.services.plugin_framework import PluginManager

router = APIRouter(prefix="/api/v2/plugins", tags=["plugins"])

_manager = PluginManager()


@router.get("", response_model=list[FaultPlugin])
async def list_plugins(status: PluginStatus | None = None):
    return _manager.list_plugins(status=status)


@router.get("/{plugin_name}", response_model=FaultPlugin)
async def get_plugin(plugin_name: str):
    plugin = _manager.get(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")
    return plugin


@router.post("/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    if not _manager.enable(plugin_name):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")
    return {"status": "enabled"}


@router.post("/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    if not _manager.disable(plugin_name):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")
    return {"status": "disabled"}


@router.post("/{plugin_name}/execute", response_model=FaultPluginExecution)
async def execute_plugin(plugin_name: str, scenario_id: str, config: dict[str, Any] | None = None):
    from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType
    from api_chaos_agent.models.schema import Endpoint, HttpMethod
    scenario = ChaosScenario(
        id=scenario_id,
        name=f"plugin-{plugin_name}",
        scenario_type=ChaosScenarioType.CUSTOM_PLUGIN,
        endpoint=Endpoint(path="/plugin/execute", method=HttpMethod.POST),
    )
    result = await _manager.execute(plugin_name, scenario, config or {})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Plugin execution failed")
    return result


@router.post("/load/directory")
async def load_plugins_from_directory(directory: str):
    loaded = _manager.load_from_directory(directory)
    return {"loaded": len(loaded), "plugins": [p.manifest.name for p in loaded]}


@router.post("/load/entrypoint")
async def load_plugin_from_entrypoint(module_path: str):
    plugin = _manager.load_from_entrypoint(module_path)
    if not plugin:
        raise HTTPException(status_code=400, detail="Failed to load plugin")
    return {"loaded": plugin.manifest.name}
