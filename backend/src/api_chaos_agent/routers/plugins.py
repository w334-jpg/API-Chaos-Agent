"""API routes for fault plugin management (Phase 2)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from api_chaos_agent.core.deps import PluginManagerDep
from api_chaos_agent.core.exceptions import NotFoundError, PluginError, RequestError, SecurityError
from api_chaos_agent.models.plugin import FaultPlugin, FaultPluginExecution, PluginStatus

router = APIRouter(prefix="/api/v2/plugins", tags=["plugins"])

_ALLOWED_PLUGIN_DIRS: list[str] = [
    d.strip() for d in os.environ.get("API_CHAOS_AGENT_PLUGIN_DIRS", "").split(":") if d.strip()
]
if not _ALLOWED_PLUGIN_DIRS:
    _ALLOWED_PLUGIN_DIRS = [
        str(Path.cwd() / "plugins"),
        str(Path.home() / ".api-chaos-agent" / "plugins"),
    ]


def _validate_plugin_directory(directory: str) -> str:
    resolved = str(Path(directory).resolve())
    for allowed in _ALLOWED_PLUGIN_DIRS:
        if resolved.startswith(str(Path(allowed).resolve())):
            return resolved
    raise SecurityError(
        detail=f"Plugin directory '{directory}' is not in the allowed list. "
        f"Allowed directories: {_ALLOWED_PLUGIN_DIRS}",
    )


@router.get("", response_model=list[FaultPlugin])
async def list_plugins(manager: PluginManagerDep, status: PluginStatus | None = None):
    return manager.list_plugins(status=status)


@router.get("/{plugin_name}", response_model=FaultPlugin)
async def get_plugin(manager: PluginManagerDep, plugin_name: str):
    plugin = manager.get(plugin_name)
    if not plugin:
        raise NotFoundError(detail=f"Plugin '{plugin_name}' not found")
    return plugin


@router.post("/{plugin_name}/enable")
async def enable_plugin(manager: PluginManagerDep, plugin_name: str):
    if not manager.enable(plugin_name):
        raise NotFoundError(detail=f"Plugin '{plugin_name}' not found")
    return {"status": "enabled"}


@router.post("/{plugin_name}/disable")
async def disable_plugin(manager: PluginManagerDep, plugin_name: str):
    if not manager.disable(plugin_name):
        raise NotFoundError(detail=f"Plugin '{plugin_name}' not found")
    return {"status": "disabled"}


@router.post("/{plugin_name}/execute", response_model=FaultPluginExecution)
async def execute_plugin(
    manager: PluginManagerDep,
    plugin_name: str,
    scenario_id: str,
    config: dict[str, Any] | None = None,
):
    plugin = manager.get(plugin_name)
    if not plugin:
        raise NotFoundError(detail=f"Plugin '{plugin_name}' not found")

    from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType
    from api_chaos_agent.models.schema import Endpoint, HttpMethod

    scenario = ChaosScenario(
        id=scenario_id,
        name=f"plugin-{plugin_name}",
        scenario_type=ChaosScenarioType.CUSTOM_PLUGIN,
        endpoint=Endpoint(path="/plugin/execute", method=HttpMethod.POST),
    )
    try:
        result = await manager.execute(plugin_name, scenario, config or {})
    except Exception as exc:
        raise PluginError(detail=str(exc))
    if not result.success:
        raise PluginError(detail=result.error or "Plugin execution failed")
    return result


@router.post("/load/directory")
async def load_plugins_from_directory(manager: PluginManagerDep, directory: str):
    validated_dir = _validate_plugin_directory(directory)
    loaded = manager.load_from_directory(validated_dir)
    return {"loaded": len(loaded), "plugins": [p.manifest.name for p in loaded]}


@router.post("/load/entrypoint")
async def load_plugin_from_entrypoint(manager: PluginManagerDep, module_path: str):
    plugin = manager.load_from_entrypoint(module_path)
    if not plugin:
        raise RequestError(detail=f"Failed to load plugin from entrypoint: {module_path}")
    return {"loaded": plugin.manifest.name}
