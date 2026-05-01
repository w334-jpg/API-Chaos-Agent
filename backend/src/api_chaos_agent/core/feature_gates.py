"""Feature gating and plan-based access control.

Provides decorators and utilities for restricting features based on
tenant plan level (Free/Pro/Enterprise). Uses custom exceptions
for consistent error response format.

Licensed under the Business Source License 1.1 (BSL 1.1).
See LICENSE.BSL for details. Change Date: 2029-04-30.
Use of this file in production requires a valid commercial license
unless your organization qualifies under the Additional Use Grant.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from api_chaos_agent.core.exceptions import AuthenticationError, SecurityError
from api_chaos_agent.models.tenant import TenantPlan, TenantQuota, PRO_QUOTA, ENTERPRISE_QUOTA

FEATURE_GATES: dict[str, dict[str, bool]] = {
    "distributed_execution": {"free": False, "pro": True, "enterprise": True},
    "custom_plugins": {"free": False, "pro": True, "enterprise": True},
    "cicd_integration": {"free": False, "pro": True, "enterprise": True},
    "advanced_analytics": {"free": False, "pro": True, "enterprise": True},
    "sso": {"free": False, "pro": False, "enterprise": True},
    "graphql_support": {"free": False, "pro": True, "enterprise": True},
    "grpc_support": {"free": False, "pro": True, "enterprise": True},
    "team_collaboration": {"free": False, "pro": True, "enterprise": True},
    "api_key_management": {"free": False, "pro": True, "enterprise": True},
    "audit_log_export": {"free": False, "pro": False, "enterprise": True},
    "custom_branding": {"free": False, "pro": False, "enterprise": True},
    "sla_guarantee": {"free": False, "pro": True, "enterprise": True},
    "priority_support": {"free": False, "pro": True, "enterprise": True},
    "dedicated_instance": {"free": False, "pro": False, "enterprise": True},
}

PLAN_QUOTAS: dict[TenantPlan, TenantQuota] = {
    TenantPlan.FREE: TenantQuota(),
    TenantPlan.PRO: PRO_QUOTA,
    TenantPlan.ENTERPRISE: ENTERPRISE_QUOTA,
}


def is_feature_available(plan: TenantPlan | str, feature: str) -> bool:
    plan_str = plan.value if isinstance(plan, TenantPlan) else plan
    gates = FEATURE_GATES.get(feature)
    if not gates:
        return True
    return gates.get(plan_str, False)


_PLAN_HIERARCHY: dict[TenantPlan, int] = {
    TenantPlan.FREE: 0,
    TenantPlan.PRO: 1,
    TenantPlan.ENTERPRISE: 2,
}


def require_plan(*allowed_plans: TenantPlan):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tenant = kwargs.get("tenant") or kwargs.get("current_tenant")
            if tenant is None:
                for arg in args:
                    if hasattr(arg, "plan"):
                        tenant = arg
                        break
            if tenant is None:
                raise AuthenticationError(detail="Tenant context required")
            min_level = min(_PLAN_HIERARCHY.get(p, 0) for p in allowed_plans)
            tenant_level = _PLAN_HIERARCHY.get(tenant.plan, 0)
            if tenant_level < min_level:
                allowed_names = ", ".join(p.value for p in allowed_plans)
                raise SecurityError(
                    detail=f"This feature requires {allowed_names} plan or above",
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_feature(feature: str):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tenant = kwargs.get("tenant") or kwargs.get("current_tenant")
            if tenant is None:
                for arg in args:
                    if hasattr(arg, "plan"):
                        tenant = arg
                        break
            if tenant is None:
                raise AuthenticationError(detail="Tenant context required")
            if not is_feature_available(tenant.plan, feature):
                raise SecurityError(
                    detail=f"Feature '{feature}' is not available on your current plan ({tenant.plan.value}). Please upgrade.",
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def get_quota_for_plan(plan: TenantPlan) -> TenantQuota:
    return PLAN_QUOTAS.get(plan, TenantQuota())


def get_features_for_plan(plan: TenantPlan) -> dict[str, bool]:
    plan_str = plan.value
    return {feature: gates.get(plan_str, False) for feature, gates in FEATURE_GATES.items()}


def check_quota(plan: TenantPlan, resource: str, current_usage: int) -> bool:
    quota = get_quota_for_plan(plan)
    limit = getattr(quota, resource, None)
    if limit is None:
        return True
    return current_usage < limit
