"""Multi-tenant models.

Defines the data structures for tenant management, including plans,
quotas, team membership, and invitations.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TenantPlan(StrEnum):
    """Subscription plan tiers."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TenantStatus(StrEnum):
    """Tenant account status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class TenantQuota(BaseModel):
    """Resource quotas for a tenant plan."""

    max_schemas: int = Field(default=10, description="Maximum API schemas allowed")
    max_scenarios_per_schema: int = Field(default=50, description="Maximum scenarios per schema")
    max_concurrent_executions: int = Field(
        default=1, description="Maximum concurrent test executions"
    )
    max_team_members: int = Field(default=1, description="Maximum team members")
    max_retention_days: int = Field(default=30, description="Data retention period in days")
    distributed_workers: int = Field(default=1, description="Maximum distributed workers")
    custom_plugins: bool = Field(default=False, description="Whether custom plugins are allowed")
    ci_cd_integration: bool = Field(
        default=False, description="Whether CI/CD integration is allowed"
    )
    sso_enabled: bool = Field(default=False, description="Whether SSO is enabled")
    advanced_analytics: bool = Field(
        default=False, description="Whether advanced analytics are available"
    )


PRO_QUOTA = TenantQuota(
    max_schemas=100,
    max_scenarios_per_schema=500,
    max_concurrent_executions=5,
    max_team_members=10,
    max_retention_days=365,
    distributed_workers=5,
    custom_plugins=True,
    ci_cd_integration=True,
    advanced_analytics=True,
)

ENTERPRISE_QUOTA = TenantQuota(
    max_schemas=10000,
    max_scenarios_per_schema=10000,
    max_concurrent_executions=50,
    max_team_members=1000,
    max_retention_days=3650,
    distributed_workers=100,
    custom_plugins=True,
    ci_cd_integration=True,
    sso_enabled=True,
    advanced_analytics=True,
)


class Tenant(BaseModel):
    """A tenant account with plan and quota information."""

    id: str = Field(default="", description="Unique tenant identifier")
    name: str = Field(description="Tenant display name")
    plan: TenantPlan = Field(default=TenantPlan.FREE, description="Subscription plan")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, description="Account status")
    quota: TenantQuota = Field(default_factory=TenantQuota, description="Resource quotas")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Account creation timestamp"
    )
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    settings: dict[str, Any] = Field(default_factory=dict, description="Tenant-specific settings")


class TeamMemberRole(StrEnum):
    """Roles within a tenant team."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TeamMember(BaseModel):
    """A member of a tenant team."""

    id: str = Field(default="", description="Unique member identifier")
    tenant_id: str = Field(description="Tenant this member belongs to")
    user_email: str = Field(description="Member email address")
    display_name: str = Field(default="", description="Display name")
    role: TeamMemberRole = Field(default=TeamMemberRole.MEMBER, description="Team role")
    joined_at: datetime = Field(default_factory=datetime.now, description="Join timestamp")
    last_active_at: datetime | None = Field(default=None, description="Last activity timestamp")


class TeamInvite(BaseModel):
    """An invitation to join a tenant team."""

    id: str = Field(default="", description="Unique invite identifier")
    tenant_id: str = Field(description="Tenant the invite is for")
    email: str = Field(description="Invitee email address")
    role: TeamMemberRole = Field(
        default=TeamMemberRole.MEMBER, description="Role to assign on acceptance"
    )
    invited_at: datetime = Field(default_factory=datetime.now, description="Invitation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")
    accepted: bool = Field(default=False, description="Whether the invite has been accepted")
