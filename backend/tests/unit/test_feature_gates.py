"""TDD-enhanced tests for Feature Gates — Block 8.

Covers:
- Unit tests: is_feature_available, require_plan, require_feature decorators
- Functional tests: full feature gate workflows with tenant context
- Edge cases: unknown features, string vs enum plans, boundary quotas
- Stress tests: many feature checks, concurrent access
"""

import os
import pytest
import time
import threading
from unittest.mock import MagicMock

from fastapi import HTTPException

from api_chaos_agent.core.feature_gates import (
    FEATURE_GATES,
    PLAN_QUOTAS,
    check_quota,
    get_features_for_plan,
    get_quota_for_plan,
    is_feature_available,
    require_feature,
    require_plan,
)
from api_chaos_agent.models.tenant import TenantPlan, TenantQuota, Tenant, PRO_QUOTA, ENTERPRISE_QUOTA


def _make_tenant(plan: TenantPlan = TenantPlan.FREE) -> Tenant:
    return Tenant(
        id="test-tenant",
        name="Test Org",
        plan=plan,
    )


class TestFeatureGateConstants:
    """Tests for FEATURE_GATES and PLAN_QUOTAS constants."""

    def test_all_features_have_three_plans(self):
        for feature, gates in FEATURE_GATES.items():
            assert set(gates.keys()) == {"free", "pro", "enterprise"}, f"{feature} missing plan keys"

    def test_free_plan_has_no_true_gates(self):
        for feature, gates in FEATURE_GATES.items():
            assert gates["free"] is False, f"{feature} should be False for free"

    def test_enterprise_has_all_features(self):
        for feature, gates in FEATURE_GATES.items():
            assert gates["enterprise"] is True, f"{feature} should be True for enterprise"

    def test_pro_features_are_subset_of_enterprise(self):
        for feature, gates in FEATURE_GATES.items():
            if gates["pro"]:
                assert gates["enterprise"], f"{feature}: pro=True but enterprise=False"

    def test_minimum_feature_count(self):
        assert len(FEATURE_GATES) >= 14

    def test_plan_quotas_has_all_plans(self):
        assert TenantPlan.FREE in PLAN_QUOTAS
        assert TenantPlan.PRO in PLAN_QUOTAS
        assert TenantPlan.ENTERPRISE in PLAN_QUOTAS

    def test_pro_quota_matches_constant(self):
        assert PLAN_QUOTAS[TenantPlan.PRO] == PRO_QUOTA

    def test_enterprise_quota_matches_constant(self):
        assert PLAN_QUOTAS[TenantPlan.ENTERPRISE] == ENTERPRISE_QUOTA

    def test_sso_is_enterprise_only(self):
        assert not FEATURE_GATES["sso"]["pro"]
        assert FEATURE_GATES["sso"]["enterprise"]

    def test_audit_log_is_enterprise_only(self):
        assert not FEATURE_GATES["audit_log_export"]["pro"]
        assert FEATURE_GATES["audit_log_export"]["enterprise"]

    def test_custom_branding_is_enterprise_only(self):
        assert not FEATURE_GATES["custom_branding"]["pro"]
        assert FEATURE_GATES["custom_branding"]["enterprise"]

    def test_dedicated_instance_is_enterprise_only(self):
        assert not FEATURE_GATES["dedicated_instance"]["pro"]
        assert FEATURE_GATES["dedicated_instance"]["enterprise"]


class TestIsFeatureAvailable:
    """Tests for is_feature_available function."""

    def test_free_plan_all_features(self):
        for feature in FEATURE_GATES:
            result = is_feature_available(TenantPlan.FREE, feature)
            assert result is False

    def test_pro_plan_pro_features(self):
        pro_features = [f for f, g in FEATURE_GATES.items() if g["pro"]]
        for feature in pro_features:
            assert is_feature_available(TenantPlan.PRO, feature) is True

    def test_pro_plan_enterprise_only_features(self):
        ent_only = [f for f, g in FEATURE_GATES.items() if not g["pro"] and g["enterprise"]]
        for feature in ent_only:
            assert is_feature_available(TenantPlan.PRO, feature) is False

    def test_enterprise_plan_all_features(self):
        for feature in FEATURE_GATES:
            assert is_feature_available(TenantPlan.ENTERPRISE, feature) is True

    def test_unknown_feature_returns_true(self):
        assert is_feature_available(TenantPlan.FREE, "nonexistent") is True
        assert is_feature_available(TenantPlan.PRO, "nonexistent") is True
        assert is_feature_available(TenantPlan.ENTERPRISE, "nonexistent") is True

    def test_string_plan_free(self):
        assert is_feature_available("free", "distributed_execution") is False

    def test_string_plan_pro(self):
        assert is_feature_available("pro", "distributed_execution") is True

    def test_string_plan_enterprise(self):
        assert is_feature_available("enterprise", "sso") is True

    def test_unknown_string_plan(self):
        assert is_feature_available("unknown_plan", "distributed_execution") is False

    def test_empty_feature_string(self):
        assert is_feature_available(TenantPlan.FREE, "") is True

    def test_specific_feature_gate_values(self):
        assert is_feature_available(TenantPlan.FREE, "graphql_support") is False
        assert is_feature_available(TenantPlan.PRO, "graphql_support") is True
        assert is_feature_available(TenantPlan.FREE, "grpc_support") is False
        assert is_feature_available(TenantPlan.PRO, "grpc_support") is True


class TestRequirePlanDecorator:
    """Tests for require_plan decorator."""

    @pytest.mark.asyncio
    async def test_allowed_plan_passes(self):
        @require_plan(TenantPlan.PRO, TenantPlan.ENTERPRISE)
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        result = await protected_func(tenant=tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_disallowed_plan_raises_403(self):
        @require_plan(TenantPlan.PRO, TenantPlan.ENTERPRISE)
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.FREE)
        with pytest.raises(HTTPException) as exc_info:
            await protected_func(tenant=tenant)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_tenant_raises_401(self):
        @require_plan(TenantPlan.PRO)
        async def protected_func():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await protected_func()
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_enterprise_passes_pro_requirement(self):
        @require_plan(TenantPlan.PRO)
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.ENTERPRISE)
        result = await protected_func(tenant=tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_tenant_from_args(self):
        @require_plan(TenantPlan.PRO)
        async def protected_func(some_arg, tenant):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        result = await protected_func("data", tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_tenant_from_current_tenant_kwarg(self):
        @require_plan(TenantPlan.PRO)
        async def protected_func(current_tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        result = await protected_func(current_tenant=tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_single_plan_requirement(self):
        @require_plan(TenantPlan.ENTERPRISE)
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        with pytest.raises(HTTPException) as exc_info:
            await protected_func(tenant=tenant)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_free_plan_rejected_for_pro_feature(self):
        @require_plan(TenantPlan.PRO, TenantPlan.ENTERPRISE)
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.FREE)
        with pytest.raises(HTTPException):
            await protected_func(tenant=tenant)


class TestRequireFeatureDecorator:
    """Tests for require_feature decorator."""

    @pytest.mark.asyncio
    async def test_available_feature_passes(self):
        @require_feature("distributed_execution")
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        result = await protected_func(tenant=tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_unavailable_feature_raises_403(self):
        @require_feature("distributed_execution")
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.FREE)
        with pytest.raises(HTTPException) as exc_info:
            await protected_func(tenant=tenant)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_enterprise_feature_on_pro_raises_403(self):
        @require_feature("sso")
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        with pytest.raises(HTTPException) as exc_info:
            await protected_func(tenant=tenant)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_enterprise_feature_on_enterprise_passes(self):
        @require_feature("sso")
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.ENTERPRISE)
        result = await protected_func(tenant=tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_no_tenant_raises_401(self):
        @require_feature("distributed_execution")
        async def protected_func():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await protected_func()
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_feature_passes(self):
        @require_feature("nonexistent_feature")
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.FREE)
        result = await protected_func(tenant=tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_error_message_includes_feature_and_plan(self):
        @require_feature("sso")
        async def protected_func(tenant=None):
            return "success"

        tenant = _make_tenant(TenantPlan.PRO)
        with pytest.raises(HTTPException) as exc_info:
            await protected_func(tenant=tenant)
        assert "sso" in exc_info.value.detail
        assert "pro" in exc_info.value.detail


class TestGetFeaturesForPlan:
    """Tests for get_features_for_plan function."""

    def test_free_all_false(self):
        features = get_features_for_plan(TenantPlan.FREE)
        for feature, available in features.items():
            assert available is False

    def test_enterprise_all_true(self):
        features = get_features_for_plan(TenantPlan.ENTERPRISE)
        for feature, available in features.items():
            assert available is True

    def test_pro_mixed(self):
        features = get_features_for_plan(TenantPlan.PRO)
        pro_true = [f for f, v in features.items() if v]
        pro_false = [f for f, v in features.items() if not v]
        assert len(pro_true) > 0
        assert len(pro_false) > 0

    def test_count_matches_feature_gates(self):
        for plan in TenantPlan:
            features = get_features_for_plan(plan)
            assert len(features) == len(FEATURE_GATES)

    def test_pro_features_subset_of_enterprise(self):
        pro_features = get_features_for_plan(TenantPlan.PRO)
        ent_features = get_features_for_plan(TenantPlan.ENTERPRISE)
        for feature in pro_features:
            if pro_features[feature]:
                assert ent_features[feature]


class TestGetQuotaForPlan:
    """Tests for get_quota_for_plan function."""

    def test_free_quota(self):
        quota = get_quota_for_plan(TenantPlan.FREE)
        assert quota.max_schemas == 10
        assert quota.max_concurrent_executions == 1
        assert quota.max_team_members == 1
        assert quota.max_scenarios_per_schema == 50
        assert not quota.custom_plugins
        assert not quota.ci_cd_integration
        assert not quota.sso_enabled
        assert not quota.advanced_analytics

    def test_pro_quota(self):
        quota = get_quota_for_plan(TenantPlan.PRO)
        assert quota.max_schemas == 100
        assert quota.max_concurrent_executions == 5
        assert quota.max_team_members == 10
        assert quota.custom_plugins
        assert quota.ci_cd_integration
        assert quota.advanced_analytics
        assert not quota.sso_enabled

    def test_enterprise_quota(self):
        quota = get_quota_for_plan(TenantPlan.ENTERPRISE)
        assert quota.max_schemas == 10000
        assert quota.max_concurrent_executions == 50
        assert quota.max_team_members == 1000
        assert quota.custom_plugins
        assert quota.ci_cd_integration
        assert quota.sso_enabled
        assert quota.advanced_analytics

    def test_quota_escalation(self):
        free = get_quota_for_plan(TenantPlan.FREE)
        pro = get_quota_for_plan(TenantPlan.PRO)
        ent = get_quota_for_plan(TenantPlan.ENTERPRISE)
        assert pro.max_schemas > free.max_schemas
        assert ent.max_schemas > pro.max_schemas
        assert pro.max_concurrent_executions > free.max_concurrent_executions
        assert ent.max_concurrent_executions > pro.max_concurrent_executions


class TestCheckQuota:
    """Tests for check_quota function."""

    def test_within_limit(self):
        assert check_quota(TenantPlan.FREE, "max_schemas", 5)
        assert check_quota(TenantPlan.PRO, "max_schemas", 50)
        assert check_quota(TenantPlan.ENTERPRISE, "max_schemas", 5000)

    def test_at_limit(self):
        assert not check_quota(TenantPlan.FREE, "max_schemas", 10)
        assert not check_quota(TenantPlan.PRO, "max_schemas", 100)
        assert not check_quota(TenantPlan.ENTERPRISE, "max_schemas", 10000)

    def test_over_limit(self):
        assert not check_quota(TenantPlan.FREE, "max_schemas", 11)
        assert not check_quota(TenantPlan.PRO, "max_schemas", 101)

    def test_unknown_resource_always_allowed(self):
        assert check_quota(TenantPlan.FREE, "nonexistent", 999999)
        assert check_quota(TenantPlan.PRO, "nonexistent", 0)

    def test_zero_usage_always_allowed(self):
        assert check_quota(TenantPlan.FREE, "max_schemas", 0)
        assert check_quota(TenantPlan.PRO, "max_schemas", 0)

    def test_concurrent_executions_quota(self):
        assert check_quota(TenantPlan.FREE, "max_concurrent_executions", 0)
        assert not check_quota(TenantPlan.FREE, "max_concurrent_executions", 1)
        assert check_quota(TenantPlan.PRO, "max_concurrent_executions", 4)
        assert not check_quota(TenantPlan.PRO, "max_concurrent_executions", 5)

    def test_team_members_quota(self):
        assert check_quota(TenantPlan.FREE, "max_team_members", 0)
        assert not check_quota(TenantPlan.FREE, "max_team_members", 1)
        assert check_quota(TenantPlan.PRO, "max_team_members", 9)
        assert not check_quota(TenantPlan.PRO, "max_team_members", 10)

    def test_scenarios_per_schema_quota(self):
        assert check_quota(TenantPlan.FREE, "max_scenarios_per_schema", 49)
        assert not check_quota(TenantPlan.FREE, "max_scenarios_per_schema", 50)


class TestFeatureGateEdgeCases:
    """Edge cases and boundary conditions."""

    def test_feature_gate_case_sensitivity(self):
        assert is_feature_available(TenantPlan.FREE, "DISTRIBUTED_EXECUTION") is True
        assert is_feature_available(TenantPlan.FREE, "distributed_execution") is False

    def test_plan_string_case_sensitivity(self):
        assert is_feature_available("FREE", "distributed_execution") is False
        assert is_feature_available("Free", "distributed_execution") is False

    def test_quota_with_negative_usage(self):
        assert check_quota(TenantPlan.FREE, "max_schemas", -1)

    def test_quota_with_very_large_usage(self):
        assert not check_quota(TenantPlan.ENTERPRISE, "max_schemas", 999999)

    @pytest.mark.asyncio
    async def test_multiple_require_plan_decorators(self):
        @require_plan(TenantPlan.PRO)
        @require_plan(TenantPlan.ENTERPRISE)
        async def double_protected(tenant=None):
            return "success"

        tenant_pro = _make_tenant(TenantPlan.PRO)
        with pytest.raises(HTTPException):
            await double_protected(tenant=tenant_pro)

    def test_get_features_for_plan_returns_new_dict(self):
        f1 = get_features_for_plan(TenantPlan.PRO)
        f2 = get_features_for_plan(TenantPlan.PRO)
        assert f1 == f2
        assert f1 is not f2


class TestFeatureGateStress:
    """Stress tests for feature gate operations."""

    def test_many_feature_checks(self):
        start = time.monotonic()
        for _ in range(10000):
            for feature in FEATURE_GATES:
                is_feature_available(TenantPlan.PRO, feature)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"10000*{len(FEATURE_GATES)} checks took {elapsed:.2f}s"

    def test_many_quota_checks(self):
        start = time.monotonic()
        for _ in range(10000):
            check_quota(TenantPlan.PRO, "max_schemas", 50)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"10000 quota checks took {elapsed:.2f}s"

    def test_concurrent_feature_checks(self):
        errors = []

        def checker():
            try:
                for _ in range(1000):
                    assert is_feature_available(TenantPlan.PRO, "distributed_execution")
                    assert not is_feature_available(TenantPlan.FREE, "distributed_execution")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=checker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_quota_checks(self):
        errors = []

        def checker():
            try:
                for _ in range(1000):
                    assert check_quota(TenantPlan.PRO, "max_schemas", 50)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=checker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
