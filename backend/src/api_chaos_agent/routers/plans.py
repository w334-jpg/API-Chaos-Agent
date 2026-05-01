from __future__ import annotations

# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.
from fastapi import APIRouter

from api_chaos_agent.core.exceptions import RequestError
from api_chaos_agent.core.feature_gates import (
    check_quota,
    get_features_for_plan,
    get_quota_for_plan,
    is_feature_available,
)
from api_chaos_agent.models.tenant import TenantPlan

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/features")
async def list_features(plan: str = "free"):
    try:
        tenant_plan = TenantPlan(plan)
    except ValueError:
        raise RequestError(detail=f"Invalid plan: {plan}")
    return {
        "plan": plan,
        "features": get_features_for_plan(tenant_plan),
        "quota": get_quota_for_plan(tenant_plan).model_dump(),
    }


@router.get("/compare")
async def compare_plans():
    result = {}
    for plan in TenantPlan:
        result[plan.value] = {
            "features": get_features_for_plan(plan),
            "quota": get_quota_for_plan(plan).model_dump(),
        }
    return result


@router.get("/check-feature")
async def check_feature(feature: str, plan: str = "free"):
    try:
        tenant_plan = TenantPlan(plan)
    except ValueError:
        raise RequestError(detail=f"Invalid plan: {plan}")
    return {
        "feature": feature,
        "plan": plan,
        "available": is_feature_available(tenant_plan, feature),
    }


@router.get("/check-quota")
async def check_quota_endpoint(resource: str, current_usage: int, plan: str = "free"):
    try:
        tenant_plan = TenantPlan(plan)
    except ValueError:
        raise RequestError(detail=f"Invalid plan: {plan}")
    return {
        "resource": resource,
        "plan": plan,
        "within_limit": check_quota(tenant_plan, resource, current_usage),
    }
