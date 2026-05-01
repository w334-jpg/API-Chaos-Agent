"""API routes for multi-tenant management (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter

from api_chaos_agent.core.exceptions import NotFoundError, RequestError, SchemaError

from api_chaos_agent.core.deps import TenantServiceDep
from api_chaos_agent.models.tenant import (
    TeamInvite,
    TeamMember,
    TeamMemberRole,
    Tenant,
    TenantPlan,
)

router = APIRouter(prefix="/api/v2/tenants", tags=["tenants"])


@router.post("", response_model=Tenant)
async def create_tenant(service: TenantServiceDep, name: str, plan: TenantPlan = TenantPlan.FREE):
    if not name or not name.strip():
        raise RequestError(detail="Tenant name must not be empty")
    return service.create_tenant(name=name, plan=plan)


@router.get("", response_model=list[Tenant])
async def list_tenants(service: TenantServiceDep):
    return service.list_tenants()


@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(service: TenantServiceDep, tenant_id: str):
    tenant = service.get_tenant(tenant_id)
    if not tenant:
        raise NotFoundError(detail="Tenant not found")
    return tenant


@router.put("/{tenant_id}/plan", response_model=Tenant)
async def update_tenant_plan(service: TenantServiceDep, tenant_id: str, plan: TenantPlan):
    tenant = service.update_plan(tenant_id, plan)
    if not tenant:
        raise NotFoundError(detail="Tenant not found")
    return tenant


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(service: TenantServiceDep, tenant_id: str):
    if not service.suspend_tenant(tenant_id):
        raise NotFoundError(detail="Tenant not found")
    return {"status": "suspended"}


@router.get("/{tenant_id}/quota")
async def check_quota(service: TenantServiceDep, tenant_id: str, resource: str, current: int = 0):
    allowed = service.check_quota(tenant_id, resource, current)
    return {"resource": resource, "allowed": allowed, "current": current}


@router.get("/{tenant_id}/members", response_model=list[TeamMember])
async def list_members(service: TenantServiceDep, tenant_id: str):
    return service.list_members(tenant_id)


@router.post("/{tenant_id}/members", response_model=TeamMember)
async def add_member(
    service: TenantServiceDep,
    tenant_id: str,
    email: str,
    role: TeamMemberRole = TeamMemberRole.MEMBER,
    display_name: str = "",
):
    member = service.add_member(tenant_id, email, role, display_name)
    if not member:
        raise RequestError(detail="Cannot add member (quota exceeded or tenant not found)")
    return member


@router.delete("/{tenant_id}/members/{member_id}")
async def remove_member(service: TenantServiceDep, tenant_id: str, member_id: str):
    if not service.remove_member(tenant_id, member_id):
        raise RequestError(detail="Cannot remove member")
    return {"status": "removed"}


@router.put("/{tenant_id}/members/{member_id}/role")
async def update_member_role(service: TenantServiceDep, tenant_id: str, member_id: str, role: TeamMemberRole):
    if not service.update_member_role(tenant_id, member_id, role):
        raise RequestError(detail="Cannot update role")
    return {"status": "updated"}


@router.post("/{tenant_id}/invites", response_model=TeamInvite)
async def create_invite(service: TenantServiceDep, tenant_id: str, email: str, role: TeamMemberRole = TeamMemberRole.MEMBER):
    invite = service.create_invite(tenant_id, email, role)
    if not invite:
        raise NotFoundError(detail="Tenant not found")
    return invite


@router.get("/{tenant_id}/invites", response_model=list[TeamInvite])
async def list_invites(service: TenantServiceDep, tenant_id: str):
    return service.list_invites(tenant_id)


@router.post("/{tenant_id}/invites/{invite_id}/accept", response_model=TeamMember)
async def accept_invite(service: TenantServiceDep, tenant_id: str, invite_id: str):
    member = service.accept_invite(invite_id, tenant_id)
    if not member:
        raise RequestError(detail="Invalid or expired invite")
    return member
