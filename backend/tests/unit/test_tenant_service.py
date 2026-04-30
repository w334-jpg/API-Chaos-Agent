"""Unit tests for Phase 2: Tenant Service."""

import pytest

from api_chaos_agent.models.tenant import TenantPlan, TeamMemberRole
from api_chaos_agent.services.tenant_service import TenantService


class TestTenantService:
    def setup_method(self):
        self.service = TenantService()

    def test_create_tenant(self):
        tenant = self.service.create_tenant("Test Org", TenantPlan.FREE)
        assert tenant.name == "Test Org"
        assert tenant.plan == TenantPlan.FREE
        assert tenant.quota.max_schemas == 10

    def test_create_pro_tenant(self):
        tenant = self.service.create_tenant("Pro Org", TenantPlan.PRO)
        assert tenant.plan == TenantPlan.PRO
        assert tenant.quota.max_schemas == 100
        assert tenant.quota.custom_plugins is True
        assert tenant.quota.ci_cd_integration is True

    def test_create_enterprise_tenant(self):
        tenant = self.service.create_tenant("Enterprise Org", TenantPlan.ENTERPRISE)
        assert tenant.plan == TenantPlan.ENTERPRISE
        assert tenant.quota.max_schemas == 10000
        assert tenant.quota.sso_enabled is True

    def test_update_plan(self):
        tenant = self.service.create_tenant("Upgrade Test", TenantPlan.FREE)
        updated = self.service.update_plan(tenant.id, TenantPlan.PRO)
        assert updated.plan == TenantPlan.PRO
        assert updated.quota.max_schemas == 100

    def test_suspend_tenant(self):
        tenant = self.service.create_tenant("Suspend Test")
        assert self.service.suspend_tenant(tenant.id)
        assert tenant.status.value == "suspended"

    def test_check_quota_within_limit(self):
        tenant = self.service.create_tenant("Quota Test", TenantPlan.FREE)
        assert self.service.check_quota(tenant.id, "schemas", 5)

    def test_check_quota_exceeded(self):
        tenant = self.service.create_tenant("Quota Exceed", TenantPlan.FREE)
        assert not self.service.check_quota(tenant.id, "schemas", 10)

    def test_add_member(self):
        tenant = self.service.create_tenant("Member Test", TenantPlan.PRO)
        member = self.service.add_member(tenant.id, "user@example.com", TeamMemberRole.MEMBER)
        assert member is not None
        assert member.user_email == "user@example.com"

    def test_add_member_quota_exceeded(self):
        tenant = self.service.create_tenant("Quota Member", TenantPlan.FREE)
        for i in range(1):
            self.service.add_member(tenant.id, f"user{i}@example.com")
        result = self.service.add_member(tenant.id, "extra@example.com")
        assert result is None

    def test_remove_member(self):
        tenant = self.service.create_tenant("Remove Test", TenantPlan.PRO)
        member = self.service.add_member(tenant.id, "remove@example.com")
        assert self.service.remove_member(tenant.id, member.id)

    def test_cannot_remove_owner(self):
        tenant = self.service.create_tenant("Owner Test", TenantPlan.PRO)
        members = self.service.list_members(tenant.id)
        owner = next(m for m in members if m.role == TeamMemberRole.OWNER)
        assert not self.service.remove_member(tenant.id, owner.id)

    def test_update_member_role(self):
        tenant = self.service.create_tenant("Role Test", TenantPlan.PRO)
        member = self.service.add_member(tenant.id, "role@example.com", TeamMemberRole.MEMBER)
        assert self.service.update_member_role(tenant.id, member.id, TeamMemberRole.ADMIN)
        members = self.service.list_members(tenant.id)
        updated = next(m for m in members if m.id == member.id)
        assert updated.role == TeamMemberRole.ADMIN

    def test_create_and_accept_invite(self):
        tenant = self.service.create_tenant("Invite Test", TenantPlan.PRO)
        invite = self.service.create_invite(tenant.id, "invited@example.com", TeamMemberRole.VIEWER)
        assert invite is not None
        member = self.service.accept_invite(invite.id, tenant.id)
        assert member is not None
        assert member.user_email == "invited@example.com"

    def test_list_tenants(self):
        self.service.create_tenant("Org1")
        self.service.create_tenant("Org2")
        assert len(self.service.list_tenants()) == 2
