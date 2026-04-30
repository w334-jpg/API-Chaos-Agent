from __future__ import annotations

# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.


from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TenantPlan(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class TenantQuota(BaseModel):
    max_schemas: int = 10
    max_scenarios_per_schema: int = 50
    max_concurrent_executions: int = 1
    max_team_members: int = 1
    max_retention_days: int = 30
    distributed_workers: int = 1
    custom_plugins: bool = False
    ci_cd_integration: bool = False
    sso_enabled: bool = False
    advanced_analytics: bool = False


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
    id: str = ""
    name: str
    plan: TenantPlan = TenantPlan.FREE
    status: TenantStatus = TenantStatus.ACTIVE
    quota: TenantQuota = Field(default_factory=TenantQuota)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    settings: dict[str, Any] = Field(default_factory=dict)


class TeamMemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TeamMember(BaseModel):
    id: str = ""
    tenant_id: str
    user_email: str
    display_name: str = ""
    role: TeamMemberRole = TeamMemberRole.MEMBER
    joined_at: datetime = Field(default_factory=datetime.now)
    last_active_at: datetime | None = None


class TeamInvite(BaseModel):
    id: str = ""
    tenant_id: str
    email: str
    role: TeamMemberRole = TeamMemberRole.MEMBER
    invited_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = None
    accepted: bool = False
