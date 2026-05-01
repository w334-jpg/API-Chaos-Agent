"""Enhanced TDD tests for Phase 2: Tenant Service.

Covers: unit tests, functional tests, edge cases, stress tests.
"""

import time

import pytest

from api_chaos_agent.models.tenant import (
    ENTERPRISE_QUOTA,
    PRO_QUOTA,
    TeamMemberRole,
    TenantPlan,
    TenantQuota,
    TenantStatus,
)
from api_chaos_agent.services.tenant_service import TenantService


class TestTenantServiceUnit:
    def setup_method(self):
        self.service = TenantService()

    def test_create_tenant_default_plan(self):
        tenant = self.service.create_tenant("Test Org")
        assert tenant.name == "Test Org"
        assert tenant.plan == TenantPlan.FREE
        assert tenant.status == TenantStatus.ACTIVE
        assert tenant.id

    def test_create_tenant_pro_plan(self):
        tenant = self.service.create_tenant("Pro Org", plan=TenantPlan.PRO)
        assert tenant.plan == TenantPlan.PRO
        assert tenant.quota.max_schemas == 100

    def test_create_tenant_enterprise_plan(self):
        tenant = self.service.create_tenant("Ent Org", plan=TenantPlan.ENTERPRISE)
        assert tenant.plan == TenantPlan.ENTERPRISE
        assert tenant.quota.max_schemas == 10000

    def test_get_tenant(self):
        tenant = self.service.create_tenant("Get Org")
        found = self.service.get_tenant(tenant.id)
        assert found is not None
        assert found.name == "Get Org"

    def test_get_nonexistent_tenant(self):
        assert self.service.get_tenant("nonexistent") is None

    def test_list_tenants(self):
        self.service.create_tenant("Org1")
        self.service.create_tenant("Org2")
        assert len(self.service.list_tenants()) == 2

    def test_update_plan(self):
        tenant = self.service.create_tenant("Upgrade Org")
        updated = self.service.update_plan(tenant.id, TenantPlan.PRO)
        assert updated is not None
        assert updated.plan == TenantPlan.PRO
        assert updated.quota.max_schemas == 100

    def test_update_plan_nonexistent(self):
        assert self.service.update_plan("nonexistent", TenantPlan.PRO) is None

    def test_update_plan_changes_quota(self):
        tenant = self.service.create_tenant("Quota Org")
        self.service.update_plan(tenant.id, TenantPlan.ENTERPRISE)
        assert tenant.quota.max_schemas == 10000
        assert tenant.quota.distributed_workers == 100
        assert tenant.quota.sso_enabled is True

    def test_suspend_tenant(self):
        tenant = self.service.create_tenant("Suspend Org")
        assert self.service.suspend_tenant(tenant.id)
        assert tenant.status == TenantStatus.SUSPENDED

    def test_suspend_nonexistent(self):
        assert not self.service.suspend_tenant("nonexistent")

    def test_tenant_ids_are_unique(self):
        t1 = self.service.create_tenant("Org1")
        t2 = self.service.create_tenant("Org2")
        assert t1.id != t2.id


class TestTenantQuotaEnforcement:
    def setup_method(self):
        self.service = TenantService()

    def test_check_quota_schemas_free(self):
        tenant = self.service.create_tenant("Free Org")
        assert self.service.check_quota(tenant.id, "schemas", 5)
        assert not self.service.check_quota(tenant.id, "schemas", 10)

    def test_check_quota_schemas_pro(self):
        tenant = self.service.create_tenant("Pro Org", plan=TenantPlan.PRO)
        assert self.service.check_quota(tenant.id, "schemas", 50)
        assert not self.service.check_quota(tenant.id, "schemas", 100)

    def test_check_quota_concurrent_executions(self):
        tenant = self.service.create_tenant("Free Org")
        assert not self.service.check_quota(tenant.id, "concurrent_executions", 1)
        assert self.service.check_quota(tenant.id, "concurrent_executions", 0)

    def test_check_quota_team_members_free(self):
        tenant = self.service.create_tenant("Free Org")
        assert not self.service.check_quota(tenant.id, "team_members", 1)
        assert self.service.check_quota(tenant.id, "team_members", 0)

    def test_check_quota_team_members_pro(self):
        tenant = self.service.create_tenant("Pro Org", plan=TenantPlan.PRO)
        assert self.service.check_quota(tenant.id, "team_members", 5)

    def test_check_quota_distributed_workers(self):
        tenant = self.service.create_tenant("Free Org")
        assert not self.service.check_quota(tenant.id, "distributed_workers", 1)
        tenant_pro = self.service.create_tenant("Pro Org", plan=TenantPlan.PRO)
        assert self.service.check_quota(tenant_pro.id, "distributed_workers", 3)

    def test_check_quota_nonexistent_tenant(self):
        assert not self.service.check_quota("nonexistent", "schemas", 0)

    def test_check_quota_unknown_resource(self):
        tenant = self.service.create_tenant("Org")
        assert not self.service.check_quota(tenant.id, "unknown_resource", 0)

    def test_free_quota_defaults(self):
        q = TenantQuota()
        assert q.max_schemas == 10
        assert q.max_scenarios_per_schema == 50
        assert q.max_concurrent_executions == 1
        assert q.max_team_members == 1
        assert q.custom_plugins is False
        assert q.ci_cd_integration is False
        assert q.sso_enabled is False
        assert q.advanced_analytics is False

    def test_pro_quota_values(self):
        assert PRO_QUOTA.max_schemas == 100
        assert PRO_QUOTA.custom_plugins is True
        assert PRO_QUOTA.ci_cd_integration is True
        assert PRO_QUOTA.advanced_analytics is True
        assert PRO_QUOTA.sso_enabled is False

    def test_enterprise_quota_values(self):
        assert ENTERPRISE_QUOTA.max_schemas == 10000
        assert ENTERPRISE_QUOTA.sso_enabled is True
        assert ENTERPRISE_QUOTA.distributed_workers == 100


class TestTeamMemberManagement:
    def setup_method(self):
        self.service = TenantService()
        self.tenant = self.service.create_tenant("Team Org", plan=TenantPlan.PRO)

    def test_owner_created_automatically(self):
        members = self.service.list_members(self.tenant.id)
        assert len(members) == 1
        assert members[0].role == TeamMemberRole.OWNER

    def test_add_member(self):
        member = self.service.add_member(self.tenant.id, "user@test.com", TeamMemberRole.MEMBER, "Test User")
        assert member is not None
        assert member.user_email == "user@test.com"
        assert member.display_name == "Test User"
        assert member.role == TeamMemberRole.MEMBER

    def test_add_member_default_display_name(self):
        member = self.service.add_member(self.tenant.id, "john@example.com")
        assert member.display_name == "john"

    def test_add_member_admin_role(self):
        member = self.service.add_member(self.tenant.id, "admin@test.com", TeamMemberRole.ADMIN)
        assert member.role == TeamMemberRole.ADMIN

    def test_add_member_viewer_role(self):
        member = self.service.add_member(self.tenant.id, "viewer@test.com", TeamMemberRole.VIEWER)
        assert member.role == TeamMemberRole.VIEWER

    def test_add_member_nonexistent_tenant(self):
        assert self.service.add_member("nonexistent", "x@test.com") is None

    def test_add_member_quota_exceeded(self):
        free_tenant = self.service.create_tenant("Free Org")
        assert self.service.add_member(free_tenant.id, "user@test.com") is None

    def test_remove_member(self):
        member = self.service.add_member(self.tenant.id, "remove@test.com")
        assert self.service.remove_member(self.tenant.id, member.id)
        assert len(self.service.list_members(self.tenant.id)) == 1

    def test_remove_owner_fails(self):
        members = self.service.list_members(self.tenant.id)
        owner = next(m for m in members if m.role == TeamMemberRole.OWNER)
        assert not self.service.remove_member(self.tenant.id, owner.id)

    def test_remove_nonexistent_member(self):
        assert not self.service.remove_member(self.tenant.id, "nonexistent")

    def test_remove_member_nonexistent_tenant(self):
        assert not self.service.remove_member("nonexistent", "some-id")

    def test_update_member_role(self):
        member = self.service.add_member(self.tenant.id, "update@test.com", TeamMemberRole.MEMBER)
        assert self.service.update_member_role(self.tenant.id, member.id, TeamMemberRole.ADMIN)
        assert member.role == TeamMemberRole.ADMIN

    def test_update_owner_role_fails(self):
        members = self.service.list_members(self.tenant.id)
        owner = next(m for m in members if m.role == TeamMemberRole.OWNER)
        assert not self.service.update_member_role(self.tenant.id, owner.id, TeamMemberRole.MEMBER)

    def test_update_nonexistent_member(self):
        assert not self.service.update_member_role(self.tenant.id, "nonexistent", TeamMemberRole.ADMIN)

    def test_list_members(self):
        self.service.add_member(self.tenant.id, "a@test.com")
        self.service.add_member(self.tenant.id, "b@test.com")
        members = self.service.list_members(self.tenant.id)
        assert len(members) == 3


class TestTeamInviteManagement:
    def setup_method(self):
        self.service = TenantService()
        self.tenant = self.service.create_tenant("Invite Org", plan=TenantPlan.PRO)

    def test_create_invite(self):
        invite = self.service.create_invite(self.tenant.id, "invite@test.com")
        assert invite is not None
        assert invite.email == "invite@test.com"
        assert invite.accepted is False
        assert invite.role == TeamMemberRole.MEMBER

    def test_create_invite_with_role(self):
        invite = self.service.create_invite(self.tenant.id, "admin@test.com", TeamMemberRole.ADMIN)
        assert invite.role == TeamMemberRole.ADMIN

    def test_create_invite_nonexistent_tenant(self):
        assert self.service.create_invite("nonexistent", "x@test.com") is None

    def test_list_invites(self):
        self.service.create_invite(self.tenant.id, "a@test.com")
        self.service.create_invite(self.tenant.id, "b@test.com")
        assert len(self.service.list_invites(self.tenant.id)) == 2

    def test_accept_invite(self):
        invite = self.service.create_invite(self.tenant.id, "accept@test.com")
        member = self.service.accept_invite(invite.id, self.tenant.id)
        assert member is not None
        assert member.user_email == "accept@test.com"
        assert invite.accepted is True

    def test_accept_invite_already_accepted(self):
        invite = self.service.create_invite(self.tenant.id, "double@test.com")
        self.service.accept_invite(invite.id, self.tenant.id)
        member2 = self.service.accept_invite(invite.id, self.tenant.id)
        assert member2 is None

    def test_accept_nonexistent_invite(self):
        assert self.service.accept_invite("nonexistent", self.tenant.id) is None

    def test_accept_invite_wrong_tenant(self):
        invite = self.service.create_invite(self.tenant.id, "wrong@test.com")
        other_tenant = self.service.create_tenant("Other Org", plan=TenantPlan.PRO)
        assert self.service.accept_invite(invite.id, other_tenant.id) is None


class TestTenantServiceEdgeCases:
    def setup_method(self):
        self.service = TenantService()

    def test_upgrade_then_downgrade_plan(self):
        tenant = self.service.create_tenant("UpDown Org", plan=TenantPlan.PRO)
        assert tenant.quota.max_schemas == 100
        self.service.update_plan(tenant.id, TenantPlan.FREE)
        assert tenant.quota.max_schemas == 10

    def test_suspend_and_continue_operations(self):
        tenant = self.service.create_tenant("Suspend Ops Org", plan=TenantPlan.PRO)
        self.service.suspend_tenant(tenant.id)
        assert tenant.status == TenantStatus.SUSPENDED
        member = self.service.add_member(tenant.id, "user@test.com")
        assert member is not None

    def test_tenant_serialization(self):
        tenant = self.service.create_tenant("Serial Org", plan=TenantPlan.PRO)
        data = tenant.model_dump()
        assert data["name"] == "Serial Org"
        assert data["plan"] == "pro"

    def test_quota_independence_between_tenants(self):
        t1 = self.service.create_tenant("Org1", plan=TenantPlan.FREE)
        t2 = self.service.create_tenant("Org2", plan=TenantPlan.PRO)
        self.service.update_plan(t1.id, TenantPlan.ENTERPRISE)
        assert t1.quota.max_schemas == 10000
        assert t2.quota.max_schemas == 100

    def test_many_members_up_to_quota(self):
        tenant = self.service.create_tenant("Big Team", plan=TenantPlan.ENTERPRISE)
        for i in range(50):
            member = self.service.add_member(tenant.id, f"user{i}@test.com")
            assert member is not None


class TestTenantServiceStress:
    def test_create_many_tenants(self):
        service = TenantService()
        for i in range(200):
            service.create_tenant(f"Org-{i}")
        assert len(service.list_tenants()) == 200

    def test_create_tenant_performance(self):
        service = TenantService()
        start = time.monotonic()
        for i in range(500):
            service.create_tenant(f"Perf-{i}")
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Creating 500 tenants took {elapsed:.3f}s"

    def test_check_quota_performance(self):
        service = TenantService()
        tenant = service.create_tenant("Quota Perf", plan=TenantPlan.PRO)
        start = time.monotonic()
        for _ in range(1000):
            service.check_quota(tenant.id, "schemas", 50)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"1000 quota checks took {elapsed:.3f}s"

    def test_add_many_members(self):
        service = TenantService()
        tenant = service.create_tenant("Big Team", plan=TenantPlan.ENTERPRISE)
        start = time.monotonic()
        for i in range(100):
            service.add_member(tenant.id, f"member{i}@test.com")
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Adding 100 members took {elapsed:.3f}s"
        assert len(service.list_members(tenant.id)) == 101
