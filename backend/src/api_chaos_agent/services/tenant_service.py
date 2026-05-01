# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""Multi-tenant service for team collaboration and tenant management.

Provides:
- Tenant CRUD with plan-based quota enforcement
- Team member management (invite, role assignment)
- Resource quota validation
- Tenant isolation for data access
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.tenant import (
    ENTERPRISE_QUOTA,
    PRO_QUOTA,
    TeamInvite,
    TeamMember,
    TeamMemberRole,
    Tenant,
    TenantPlan,
    TenantQuota,
    TenantStatus,
)

logger = get_logger(__name__)

_PLAN_QUOTAS: dict[TenantPlan, TenantQuota] = {
    TenantPlan.FREE: TenantQuota(),
    TenantPlan.PRO: PRO_QUOTA,
    TenantPlan.ENTERPRISE: ENTERPRISE_QUOTA,
}


class TenantService:
    """Manage tenants, team members, and quotas."""

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._members: dict[str, list[TeamMember]] = {}
        self._invites: dict[str, list[TeamInvite]] = {}

    def create_tenant(self, name: str, plan: TenantPlan = TenantPlan.FREE) -> Tenant:
        quota = _PLAN_QUOTAS.get(plan, TenantQuota()).model_copy()
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=name,
            plan=plan,
            quota=quota,
        )
        self._tenants[tenant.id] = tenant
        self._members[tenant.id] = []
        self._invites[tenant.id] = []
        owner = TeamMember(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            user_email="",
            display_name="Owner",
            role=TeamMemberRole.OWNER,
        )
        self._members[tenant.id].append(owner)
        logger.info("tenant_created", tenant_id=tenant.id, name=name, plan=plan.value)
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    def update_plan(self, tenant_id: str, plan: TenantPlan) -> Tenant | None:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None
        tenant.plan = plan
        tenant.quota = _PLAN_QUOTAS.get(plan, TenantQuota()).model_copy()
        tenant.updated_at = datetime.now()
        logger.info("tenant_plan_updated", tenant_id=tenant_id, plan=plan.value)
        return tenant

    def suspend_tenant(self, tenant_id: str) -> bool:
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = TenantStatus.SUSPENDED
            return True
        return False

    def check_quota(self, tenant_id: str, resource: str, current: int) -> bool:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        quota_map: dict[str, int] = {
            "schemas": tenant.quota.max_schemas,
            "scenarios": tenant.quota.max_scenarios_per_schema,
            "concurrent_executions": tenant.quota.max_concurrent_executions,
            "team_members": tenant.quota.max_team_members,
            "distributed_workers": tenant.quota.distributed_workers,
        }
        limit = quota_map.get(resource, 0)
        return current < limit

    def add_member(self, tenant_id: str, email: str, role: TeamMemberRole = TeamMemberRole.MEMBER,
                   display_name: str = "") -> TeamMember | None:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None
        members = self._members.get(tenant_id, [])
        if len(members) >= tenant.quota.max_team_members:
            logger.warning("quota_exceeded", tenant_id=tenant_id, resource="team_members")
            return None
        member = TeamMember(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_email=email,
            display_name=display_name or email.split("@")[0],
            role=role,
        )
        members.append(member)
        self._members[tenant_id] = members
        logger.info("member_added", tenant_id=tenant_id, email=email, role=role.value)
        return member

    def remove_member(self, tenant_id: str, member_id: str) -> bool:
        members = self._members.get(tenant_id, [])
        for i, m in enumerate(members):
            if m.id == member_id and m.role != TeamMemberRole.OWNER:
                members.pop(i)
                return True
        return False

    def update_member_role(self, tenant_id: str, member_id: str, role: TeamMemberRole) -> bool:
        members = self._members.get(tenant_id, [])
        for m in members:
            if m.id == member_id and m.role != TeamMemberRole.OWNER:
                m.role = role
                return True
        return False

    def list_members(self, tenant_id: str) -> list[TeamMember]:
        return self._members.get(tenant_id, [])

    def create_invite(self, tenant_id: str, email: str, role: TeamMemberRole = TeamMemberRole.MEMBER) -> TeamInvite | None:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None
        invite = TeamInvite(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            email=email,
            role=role,
        )
        self._invites.setdefault(tenant_id, []).append(invite)
        logger.info("invite_created", tenant_id=tenant_id, email=email)
        return invite

    def list_invites(self, tenant_id: str) -> list[TeamInvite]:
        return self._invites.get(tenant_id, [])

    def accept_invite(self, invite_id: str, tenant_id: str) -> TeamMember | None:
        invites = self._invites.get(tenant_id, [])
        for invite in invites:
            if invite.id == invite_id and not invite.accepted:
                invite.accepted = True
                return self.add_member(tenant_id, invite.email, invite.role)
        return None
