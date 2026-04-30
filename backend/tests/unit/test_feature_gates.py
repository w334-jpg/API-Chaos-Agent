"""Unit tests for Phase 2: Feature Gates & Tier System."""

import pytest

from api_chaos_agent.core.feature_gates import (
    FEATURE_GATES,
    check_quota,
    get_features_for_plan,
    get_quota_for_plan,
    is_feature_available,
)
from api_chaos_agent.models.tenant import TenantPlan, TenantQuota, PRO_QUOTA, ENTERPRISE_QUOTA


class TestFeatureAvailability:
    def test_free_plan_no_pro_features(self):
        for feature in ["distributed_execution", "custom_plugins", "cicd_integration", "advanced_analytics"]:
            assert not is_feature_available(TenantPlan.FREE, feature)

    def test_pro_plan_has_pro_features(self):
        for feature in ["distributed_execution", "custom_plugins", "cicd_integration", "advanced_analytics"]:
            assert is_feature_available(TenantPlan.PRO, feature)

    def test_pro_plan_no_enterprise_features(self):
        for feature in ["sso", "audit_log_export", "custom_branding", "dedicated_instance"]:
            assert not is_feature_available(TenantPlan.PRO, feature)

    def test_enterprise_plan_has_all_features(self):
        for feature in FEATURE_GATES:
            assert is_feature_available(TenantPlan.ENTERPRISE, feature)

    def test_unknown_feature_always_available(self):
        assert is_feature_available(TenantPlan.FREE, "nonexistent_feature")
        assert is_feature_available(TenantPlan.PRO, "nonexistent_feature")

    def test_plan_string_input(self):
        assert not is_feature_available("free", "distributed_execution")
        assert is_feature_available("pro", "distributed_execution")
        assert is_feature_available("enterprise", "sso")


class TestPlanQuotas:
    def test_free_quota_defaults(self):
        quota = get_quota_for_plan(TenantPlan.FREE)
        assert isinstance(quota, TenantQuota)
        assert quota.max_schemas == 10
        assert quota.max_concurrent_executions == 1
        assert quota.max_team_members == 1
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


class TestQuotaChecking:
    def test_within_limit(self):
        assert check_quota(TenantPlan.FREE, "max_schemas", 5)
        assert check_quota(TenantPlan.PRO, "max_schemas", 50)

    def test_at_limit(self):
        assert not check_quota(TenantPlan.FREE, "max_schemas", 10)
        assert not check_quota(TenantPlan.PRO, "max_schemas", 100)

    def test_over_limit(self):
        assert not check_quota(TenantPlan.FREE, "max_schemas", 15)

    def test_unknown_resource(self):
        assert check_quota(TenantPlan.FREE, "nonexistent_resource", 999)


class TestGetFeaturesForPlan:
    def test_free_features(self):
        features = get_features_for_plan(TenantPlan.FREE)
        assert isinstance(features, dict)
        assert not features.get("distributed_execution", True)
        assert not features.get("sso", True)

    def test_pro_features(self):
        features = get_features_for_plan(TenantPlan.PRO)
        assert features.get("distributed_execution", False)
        assert features.get("custom_plugins", False)
        assert not features.get("sso", True)

    def test_enterprise_features(self):
        features = get_features_for_plan(TenantPlan.ENTERPRISE)
        assert features.get("distributed_execution", False)
        assert features.get("sso", False)
        assert features.get("audit_log_export", False)

    def test_all_features_listed(self):
        features = get_features_for_plan(TenantPlan.FREE)
        assert len(features) == len(FEATURE_GATES)
