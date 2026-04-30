# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""API routes for multi-tenant management (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api_chaos_agent.models.tenant import (
    TeamInvite,
    TeamMember,
    TeamMemberRole,
    Tenant,
    TenantPlan,
)
from api_chaos_agent.services.tenant_service import TenantService

router = APIRouter(prefix="/api/v2/tenants", tags=["tenants"])

_service = TenantService()


@router.post("", response_model=Tenant)
async def create_tenant(name: str, plan: TenantPlan = TenantPlan.FREE):
    return _service.create_tenant(name=name, plan=plan)


@router.get("", response_model=list[Tenant])
async def list_tenants():
    return _service.list_tenants()


@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(tenant_id: str):
    tenant = _service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.put("/{tenant_id}/plan", response_model=Tenant)
async def update_tenant_plan(tenant_id: str, plan: TenantPlan):
    tenant = _service.update_plan(tenant_id, plan)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str):
    if not _service.suspend_tenant(tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"status": "suspended"}


@router.get("/{tenant_id}/quota")
async def check_quota(tenant_id: str, resource: str, current: int = 0):
    allowed = _service.check_quota(tenant_id, resource, current)
    return {"resource": resource, "allowed": allowed, "current": current}


@router.get("/{tenant_id}/members", response_model=list[TeamMember])
async def list_members(tenant_id: str):
    return _service.list_members(tenant_id)


@router.post("/{tenant_id}/members", response_model=TeamMember)
async def add_member(tenant_id: str, email: str, role: TeamMemberRole = TeamMemberRole.MEMBER, display_name: str = ""):
    member = _service.add_member(tenant_id, email, role, display_name)
    if not member:
        raise HTTPException(status_code=400, detail="Cannot add member (quota exceeded or tenant not found)")
    return member


@router.delete("/{tenant_id}/members/{member_id}")
async def remove_member(tenant_id: str, member_id: str):
    if not _service.remove_member(tenant_id, member_id):
        raise HTTPException(status_code=400, detail="Cannot remove member")
    return {"status": "removed"}


@router.put("/{tenant_id}/members/{member_id}/role")
async def update_member_role(tenant_id: str, member_id: str, role: TeamMemberRole):
    if not _service.update_member_role(tenant_id, member_id, role):
        raise HTTPException(status_code=400, detail="Cannot update role")
    return {"status": "updated"}


@router.post("/{tenant_id}/invites", response_model=TeamInvite)
async def create_invite(tenant_id: str, email: str, role: TeamMemberRole = TeamMemberRole.MEMBER):
    invite = _service.create_invite(tenant_id, email, role)
    if not invite:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return invite


@router.get("/{tenant_id}/invites", response_model=list[TeamInvite])
async def list_invites(tenant_id: str):
    return _service.list_invites(tenant_id)


@router.post("/{tenant_id}/invites/{invite_id}/accept", response_model=TeamMember)
async def accept_invite(tenant_id: str, invite_id: str):
    member = _service.accept_invite(invite_id, tenant_id)
    if not member:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")
    return member
