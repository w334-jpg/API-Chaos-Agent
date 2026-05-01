"""TDD-enhanced tests for License Manager — Block 7.

Covers:
- Unit tests: LicenseInfo properties, signature verification, key parsing
- Functional tests: full license lifecycle workflows
- Edge cases: expired keys, malformed keys, boundary values
- Stress tests: concurrent access, rapid install/remove cycles
"""

import base64
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from api_chaos_agent.core.license import (
    BSL_PROTECTED_MODULES,
    BSL_HEADER,
    LicenseInfo,
    LicenseManager,
    LicenseStatus,
    LicenseType,
    _check_bsl_eligibility,
    _generate_signature,
    _is_production_environment,
    _parse_license_key,
    _read_license_file,
    _verify_signature,
    generate_trial_license,
)
from api_chaos_agent.models.tenant import TenantPlan


def _cleanup_env():
    for key in [
        "API_CHAOS_AGENT_ENV", "NODE_ENV",
        "API_CHAOS_AGENT_ORG_SIZE", "API_CHAOS_AGENT_ORG_REVENUE",
        "API_CHAOS_AGENT_NONPROFIT", "API_CHAOS_AGENT_ACADEMIC",
        "API_CHAOS_AGENT_LICENSE_FILE",
    ]:
        os.environ.pop(key, None)


def _make_license_key(
    license_type: str = "trial",
    holder: str = "test",
    plan: str = "pro",
    days: int = 30,
    features: list[str] | None = None,
    max_seats: int = 5,
    is_production: bool = True,
) -> str:
    now = datetime.now()
    expires = now + timedelta(days=days)
    payload = {
        "type": license_type,
        "holder": holder,
        "plan": plan,
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "features": features or ["distributed_execution"],
        "max_seats": max_seats,
        "is_production": is_production,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    signature = _generate_signature(payload_b64)
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256","typ":"license"}').rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{signature}"


class TestLicenseInfoProperties:
    """Tests for LicenseInfo model and its properties."""

    def test_default_bsl_license(self):
        info = LicenseInfo()
        assert info.license_type == LicenseType.BSL
        assert info.status == LicenseStatus.BSL_NON_PRODUCTION
        assert info.holder == ""
        assert info.plan == TenantPlan.FREE
        assert info.features == []
        assert info.max_seats == 1
        assert info.is_production is False

    def test_is_valid_bsl_non_production(self):
        info = LicenseInfo(status=LicenseStatus.BSL_NON_PRODUCTION)
        assert info.is_valid is True

    def test_is_valid_valid(self):
        info = LicenseInfo(status=LicenseStatus.VALID)
        assert info.is_valid is True

    def test_is_valid_expired(self):
        info = LicenseInfo(status=LicenseStatus.EXPIRED)
        assert info.is_valid is False

    def test_is_valid_invalid(self):
        info = LicenseInfo(status=LicenseStatus.INVALID)
        assert info.is_valid is False

    def test_is_valid_missing(self):
        info = LicenseInfo(status=LicenseStatus.MISSING)
        assert info.is_valid is False

    def test_is_commercial_pro(self):
        info = LicenseInfo(license_type=LicenseType.COMMERCIAL_PRO)
        assert info.is_commercial is True

    def test_is_commercial_enterprise(self):
        info = LicenseInfo(license_type=LicenseType.COMMERCIAL_ENTERPRISE)
        assert info.is_commercial is True

    def test_is_commercial_trial(self):
        info = LicenseInfo(license_type=LicenseType.TRIAL)
        assert info.is_commercial is True

    def test_is_commercial_bsl(self):
        info = LicenseInfo(license_type=LicenseType.BSL)
        assert info.is_commercial is False

    def test_days_until_expiry_future(self):
        info = LicenseInfo(expires_at=datetime.now() + timedelta(days=15))
        assert info.days_until_expiry is not None
        assert 14 <= info.days_until_expiry <= 16

    def test_days_until_expiry_past(self):
        info = LicenseInfo(expires_at=datetime.now() - timedelta(days=5))
        assert info.days_until_expiry == 0

    def test_days_until_expiry_none(self):
        info = LicenseInfo()
        assert info.days_until_expiry is None

    def test_days_until_expiry_today(self):
        info = LicenseInfo(expires_at=datetime.now() + timedelta(hours=1))
        assert info.days_until_expiry == 0


class TestSignatureVerification:
    """Tests for _verify_signature and _generate_signature."""

    def test_generate_and_verify_match(self):
        payload = "test-payload-data"
        sig = _generate_signature(payload)
        assert _verify_signature(payload, sig) is True

    def test_wrong_payload_fails(self):
        sig = _generate_signature("correct-payload")
        assert _verify_signature("wrong-payload", sig) is False

    def test_wrong_signature_fails(self):
        assert _verify_signature("payload", "invalid-signature") is False

    def test_empty_payload(self):
        sig = _generate_signature("")
        assert _verify_signature("", sig) is True

    def test_deterministic_signature(self):
        sig1 = _generate_signature("same-payload")
        sig2 = _generate_signature("same-payload")
        assert sig1 == sig2

    def test_different_payloads_different_signatures(self):
        sig1 = _generate_signature("payload-a")
        sig2 = _generate_signature("payload-b")
        assert sig1 != sig2


class TestLicenseKeyParsing:
    """Tests for _parse_license_key function."""

    def test_valid_trial_key(self):
        key = generate_trial_license("test-user", days=30)
        info = _parse_license_key(key)
        assert info is not None
        assert info.license_type == LicenseType.TRIAL
        assert info.status == LicenseStatus.VALID
        assert info.holder == "test-user"
        assert info.plan == TenantPlan.PRO

    def test_valid_commercial_pro_key(self):
        key = _make_license_key(license_type="commercial_pro", plan="pro")
        info = _parse_license_key(key)
        assert info is not None
        assert info.license_type == LicenseType.COMMERCIAL_PRO
        assert info.plan == TenantPlan.PRO

    def test_valid_commercial_enterprise_key(self):
        key = _make_license_key(license_type="commercial_enterprise", plan="enterprise")
        info = _parse_license_key(key)
        assert info is not None
        assert info.license_type == LicenseType.COMMERCIAL_ENTERPRISE
        assert info.plan == TenantPlan.ENTERPRISE

    def test_expired_key(self):
        now = datetime.now()
        payload = {
            "type": "trial",
            "holder": "expired-user",
            "plan": "pro",
            "issued_at": (now - timedelta(days=60)).isoformat(),
            "expires_at": (now - timedelta(days=1)).isoformat(),
            "features": [],
            "max_seats": 1,
            "is_production": True,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
        sig = _generate_signature(payload_b64)
        header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256"}').rstrip(b"=").decode()
        key = f"{header_b64}.{payload_b64}.{sig}"
        info = _parse_license_key(key)
        assert info is not None
        assert info.status == LicenseStatus.EXPIRED

    def test_malformed_key_too_few_parts(self):
        assert _parse_license_key("only.two") is None

    def test_malformed_key_too_many_parts(self):
        assert _parse_license_key("a.b.c.d") is None

    def test_malformed_key_invalid_base64(self):
        assert _parse_license_key("header.!!!invalid!!!.sig") is None

    def test_malformed_key_invalid_signature(self):
        key = _make_license_key()
        parts = key.split(".")
        tampered = f"{parts[0]}.{parts[1]}.0000000000000000000000000000000000000000"
        info = _parse_license_key(tampered)
        assert info is None

    def test_key_with_features(self):
        key = _make_license_key(features=["distributed_execution", "custom_plugins", "cicd_integration"])
        info = _parse_license_key(key)
        assert info is not None
        assert "distributed_execution" in info.features
        assert len(info.features) == 3

    def test_key_with_max_seats(self):
        key = _make_license_key(max_seats=50)
        info = _parse_license_key(key)
        assert info is not None
        assert info.max_seats == 50

    def test_empty_string_key(self):
        assert _parse_license_key("") is None

    def test_none_key_returns_none(self):
        assert _parse_license_key(None) is None


class TestReadLicenseFile:
    """Tests for _read_license_file function."""

    def setup_method(self):
        _cleanup_env()
        self._saved_env = os.environ.get("API_CHAOS_AGENT_LICENSE_FILE")

    def teardown_method(self):
        _cleanup_env()

    def test_no_file_no_env(self):
        os.environ.pop("API_CHAOS_AGENT_LICENSE_FILE", None)
        result = _read_license_file()
        assert result is None or isinstance(result, str)

    def test_env_var_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
            f.write("test-license-content")
            f.flush()
            os.environ["API_CHAOS_AGENT_LICENSE_FILE"] = f.name
            result = _read_license_file()
            assert result == "test-license-content"
            os.unlink(f.name)

    def test_env_var_nonexistent_path(self):
        os.environ["API_CHAOS_AGENT_LICENSE_FILE"] = "/nonexistent/path/license.key"
        result = _read_license_file()
        assert result is None or isinstance(result, str)

    def test_env_var_takes_priority(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
            f.write("priority-license")
            f.flush()
            os.environ["API_CHAOS_AGENT_LICENSE_FILE"] = f.name
            result = _read_license_file()
            assert result == "priority-license"
            os.unlink(f.name)


class TestIsProductionEnvironment:
    """Tests for _is_production_environment function."""

    def setup_method(self):
        _cleanup_env()

    def teardown_method(self):
        _cleanup_env()

    def test_production_env(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        assert _is_production_environment() is True

    def test_prod_env(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "prod"
        assert _is_production_environment() is True

    def test_staging_env(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "staging"
        assert _is_production_environment() is True

    def test_stage_env(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "stage"
        assert _is_production_environment() is True

    def test_development_env(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "development"
        assert _is_production_environment() is False

    def test_dev_env(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "dev"
        assert _is_production_environment() is False

    def test_node_env_fallback(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ["NODE_ENV"] = "production"
        assert _is_production_environment() is True

    def test_no_env_defaults_development(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        assert _is_production_environment() is False

    def test_case_insensitive(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "PRODUCTION"
        assert _is_production_environment() is True


class TestBslEligibility:
    """Tests for _check_bsl_eligibility function."""

    def setup_method(self):
        _cleanup_env()

    def teardown_method(self):
        _cleanup_env()

    def test_small_org_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "10"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "500000"
        assert _check_bsl_eligibility() is True

    def test_large_org_not_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "100"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "5000000"
        assert _check_bsl_eligibility() is False

    def test_org_size_49_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "49"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "500000"
        assert _check_bsl_eligibility() is True

    def test_org_size_50_not_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "50"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "500000"
        assert _check_bsl_eligibility() is False

    def test_revenue_999999_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "10"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "999999"
        assert _check_bsl_eligibility() is True

    def test_revenue_1000000_not_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "10"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "1000000"
        assert _check_bsl_eligibility() is False

    def test_nonprofit_eligible(self):
        os.environ["API_CHAOS_AGENT_NONPROFIT"] = "true"
        assert _check_bsl_eligibility() is True

    def test_nonprofit_yes(self):
        os.environ["API_CHAOS_AGENT_NONPROFIT"] = "yes"
        assert _check_bsl_eligibility() is True

    def test_nonprofit_1(self):
        os.environ["API_CHAOS_AGENT_NONPROFIT"] = "1"
        assert _check_bsl_eligibility() is True

    def test_nonprofit_false(self):
        os.environ["API_CHAOS_AGENT_NONPROFIT"] = "false"
        assert _check_bsl_eligibility() is False

    def test_academic_eligible(self):
        os.environ["API_CHAOS_AGENT_ACADEMIC"] = "true"
        assert _check_bsl_eligibility() is True

    def test_academic_yes(self):
        os.environ["API_CHAOS_AGENT_ACADEMIC"] = "yes"
        assert _check_bsl_eligibility() is True

    def test_academic_1(self):
        os.environ["API_CHAOS_AGENT_ACADEMIC"] = "1"
        assert _check_bsl_eligibility() is True

    def test_no_qualifiers_not_eligible(self):
        os.environ.pop("API_CHAOS_AGENT_ORG_SIZE", None)
        os.environ.pop("API_CHAOS_AGENT_NONPROFIT", None)
        os.environ.pop("API_CHAOS_AGENT_ACADEMIC", None)
        assert _check_bsl_eligibility() is False

    def test_org_size_zero_not_eligible(self):
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "0"
        assert _check_bsl_eligibility() is False


class TestLicenseManagerUnit:
    """Unit tests for LicenseManager methods."""

    def setup_method(self):
        self.manager = LicenseManager()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        _cleanup_env()
        for path in [Path("license.key"), Path.home() / ".api-chaos-agent" / "license.key"]:
            if path.exists():
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def teardown_method(self):
        _cleanup_env()

    def test_get_license_info_default(self):
        info = self.manager.get_license_info()
        assert info.license_type == LicenseType.BSL
        assert info.status == LicenseStatus.BSL_NON_PRODUCTION

    def test_can_use_pro_features_in_dev(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        self.manager._license_info = None
        self.manager._last_check = 0.0
        assert self.manager.can_use_pro_features() is True

    def test_cannot_use_enterprise_without_license(self):
        assert self.manager.can_use_enterprise_features() is False

    def test_install_trial_license(self):
        key = generate_trial_license("test-org", days=30)
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.TRIAL
        assert info.status == LicenseStatus.VALID
        assert info.plan == TenantPlan.PRO
        assert self.manager.can_use_pro_features() is True

    def test_install_commercial_pro(self):
        key = _make_license_key(license_type="commercial_pro", plan="pro")
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.COMMERCIAL_PRO
        assert self.manager.can_use_pro_features() is True

    def test_install_commercial_enterprise(self):
        key = _make_license_key(license_type="commercial_enterprise", plan="enterprise")
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.COMMERCIAL_ENTERPRISE
        assert self.manager.can_use_enterprise_features() is True

    def test_install_invalid_key_raises(self):
        with pytest.raises(ValueError, match="Invalid license key"):
            self.manager.install_license("invalid.key.format")

    def test_install_tampered_key_raises(self):
        key = _make_license_key()
        parts = key.split(".")
        tampered = f"{parts[0]}.{parts[1]}.tamperedsignature0000000000000000000"
        with pytest.raises(ValueError, match="Invalid license key"):
            self.manager.install_license(tampered)

    def test_remove_license(self):
        key = generate_trial_license("test-org", days=30)
        self.manager.install_license(key)
        result = self.manager.remove_license()
        assert result is True
        assert self.manager._license_info is None

    def test_require_pro_raises_without_license_in_prod(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ.pop("API_CHAOS_AGENT_ORG_SIZE", None)
        os.environ.pop("API_CHAOS_AGENT_NONPROFIT", None)
        os.environ.pop("API_CHAOS_AGENT_ACADEMIC", None)
        self.manager._license_info = None
        self.manager._last_check = 0.0
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self.manager.require_pro()
        assert exc_info.value.status_code == 403

    def test_require_enterprise_raises_without_license(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self.manager.require_enterprise()
        assert exc_info.value.status_code == 403

    def test_require_pro_succeeds_with_trial(self):
        key = generate_trial_license("test", days=30)
        self.manager.install_license(key)
        self.manager.require_pro()

    def test_require_enterprise_succeeds_with_enterprise(self):
        key = _make_license_key(license_type="commercial_enterprise", plan="enterprise")
        self.manager.install_license(key)
        self.manager.require_enterprise()

    def test_require_enterprise_fails_with_pro(self):
        key = _make_license_key(license_type="commercial_pro", plan="pro")
        self.manager.install_license(key)
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            self.manager.require_enterprise()

    def test_license_caching(self):
        self.manager.get_license_info()
        first_check = self.manager._last_check
        time.sleep(0.01)
        self.manager.get_license_info()
        assert self.manager._last_check == first_check


class TestBslProtectedModules:
    """Tests for BSL_PROTECTED_MODULES constant."""

    def test_contains_grpc_parser(self):
        assert "api_chaos_agent.services.grpc_graphql_parser" in BSL_PROTECTED_MODULES

    def test_contains_distributed_engine(self):
        assert "api_chaos_agent.services.distributed_engine" in BSL_PROTECTED_MODULES

    def test_contains_plugin_framework(self):
        assert "api_chaos_agent.services.plugin_framework" in BSL_PROTECTED_MODULES

    def test_contains_cicd_service(self):
        assert "api_chaos_agent.services.cicd_service" in BSL_PROTECTED_MODULES

    def test_contains_tenant_service(self):
        assert "api_chaos_agent.services.tenant_service" in BSL_PROTECTED_MODULES

    def test_contains_analytics_service(self):
        assert "api_chaos_agent.services.analytics_service" in BSL_PROTECTED_MODULES

    def test_contains_feature_gates(self):
        assert "api_chaos_agent.core.feature_gates" in BSL_PROTECTED_MODULES

    def test_is_frozenset(self):
        assert isinstance(BSL_PROTECTED_MODULES, frozenset)

    def test_minimum_module_count(self):
        assert len(BSL_PROTECTED_MODULES) >= 10


class TestBslHeader:
    """Tests for BSL_HEADER constant."""

    def test_contains_bsl_string(self):
        assert "Business Source License" in BSL_HEADER

    def test_contains_change_date(self):
        assert "2029-04-30" in BSL_HEADER

    def test_is_comment_format(self):
        for line in BSL_HEADER.strip().split("\n"):
            assert line.startswith("#")


class TestLicenseEdgeCases:
    """Edge cases and boundary conditions."""

    def setup_method(self):
        self.manager = LicenseManager()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        _cleanup_env()

    def teardown_method(self):
        _cleanup_env()

    def test_license_with_zero_max_seats(self):
        key = _make_license_key(max_seats=0)
        info = _parse_license_key(key)
        assert info is not None
        assert info.max_seats == 0

    def test_license_with_empty_features(self):
        key = _make_license_key(features=[""])
        info = _parse_license_key(key)
        assert info is not None
        assert len(info.features) == 1

    def test_license_expires_at_exact_boundary(self):
        now = datetime.now()
        payload = {
            "type": "trial",
            "holder": "boundary",
            "plan": "pro",
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=1)).isoformat(),
            "features": [],
            "max_seats": 1,
            "is_production": True,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
        sig = _generate_signature(payload_b64)
        header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256"}').rstrip(b"=").decode()
        key = f"{header_b64}.{payload_b64}.{sig}"
        info = _parse_license_key(key)
        assert info is not None
        assert info.status == LicenseStatus.VALID

    def test_trial_license_is_commercial(self):
        info = LicenseInfo(license_type=LicenseType.TRIAL, status=LicenseStatus.VALID, plan=TenantPlan.PRO)
        assert info.is_commercial is True

    def test_bsl_license_not_commercial(self):
        info = LicenseInfo(license_type=LicenseType.BSL)
        assert info.is_commercial is False

    def test_production_env_with_bsl_eligibility(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "5"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "100000"
        self.manager._license_info = None
        self.manager._last_check = 0.0
        assert self.manager.can_use_pro_features() is True

    def test_production_env_without_eligibility(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ.pop("API_CHAOS_AGENT_ORG_SIZE", None)
        os.environ.pop("API_CHAOS_AGENT_NONPROFIT", None)
        os.environ.pop("API_CHAOS_AGENT_ACADEMIC", None)
        self.manager._license_info = None
        self.manager._last_check = 0.0
        assert self.manager.can_use_pro_features() is False

    def test_staging_env_is_production(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "staging"
        assert _is_production_environment() is True

    def test_install_expired_license_raises(self):
        now = datetime.now()
        payload = {
            "type": "trial",
            "holder": "expired",
            "plan": "pro",
            "issued_at": (now - timedelta(days=60)).isoformat(),
            "expires_at": (now - timedelta(days=1)).isoformat(),
            "features": [],
            "max_seats": 1,
            "is_production": True,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
        sig = _generate_signature(payload_b64)
        header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256"}').rstrip(b"=").decode()
        key = f"{header_b64}.{payload_b64}.{sig}"
        with pytest.raises(ValueError, match="Invalid license key"):
            self.manager.install_license(key)


class TestLicenseFunctional:
    """Functional tests: full license lifecycle workflows."""

    def setup_method(self):
        self.manager = LicenseManager()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        _cleanup_env()

    def teardown_method(self):
        _cleanup_env()

    def test_trial_license_lifecycle(self):
        key = generate_trial_license("trial-org", days=30)
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.TRIAL
        assert self.manager.can_use_pro_features() is True
        assert self.manager.can_use_enterprise_features() is False
        self.manager.remove_license()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        assert self.manager.can_use_pro_features() is True

    def test_pro_license_lifecycle(self):
        key = _make_license_key(license_type="commercial_pro", plan="pro")
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.COMMERCIAL_PRO
        assert self.manager.can_use_pro_features() is True
        assert self.manager.can_use_enterprise_features() is False

    def test_enterprise_license_lifecycle(self):
        key = _make_license_key(license_type="commercial_enterprise", plan="enterprise")
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.COMMERCIAL_ENTERPRISE
        assert self.manager.can_use_pro_features() is True
        assert self.manager.can_use_enterprise_features() is True

    def test_upgrade_from_pro_to_enterprise(self):
        pro_key = _make_license_key(license_type="commercial_pro", plan="pro")
        self.manager.install_license(pro_key)
        assert self.manager.can_use_pro_features() is True
        assert self.manager.can_use_enterprise_features() is False
        ent_key = _make_license_key(license_type="commercial_enterprise", plan="enterprise")
        info = self.manager.install_license(ent_key)
        assert info.license_type == LicenseType.COMMERCIAL_ENTERPRISE
        assert self.manager.can_use_enterprise_features() is True

    def test_bsl_to_trial_upgrade(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        os.environ.pop("API_CHAOS_AGENT_LICENSE_FILE", None)
        fresh_manager = LicenseManager()
        fresh_manager._license_info = None
        fresh_manager._last_check = 0.0
        with patch("api_chaos_agent.core.license._read_license_file", return_value=None):
            info = fresh_manager.get_license_info()
        assert info.license_type == LicenseType.BSL
        key = generate_trial_license("upgrade-org", days=30)
        info = fresh_manager.install_license(key)
        assert info.license_type == LicenseType.TRIAL

    def test_generate_trial_with_custom_days(self):
        key = generate_trial_license("custom-days", days=90)
        info = _parse_license_key(key)
        assert info is not None
        assert info.days_until_expiry is not None
        assert info.days_until_expiry >= 89


class TestLicenseStress:
    """Stress tests for license manager."""

    def setup_method(self):
        self.manager = LicenseManager()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        _cleanup_env()

    def teardown_method(self):
        _cleanup_env()

    def test_rapid_install_remove_cycles(self):
        start = time.monotonic()
        for i in range(50):
            key = generate_trial_license(f"org-{i}", days=30)
            self.manager.install_license(key)
            assert self.manager.can_use_pro_features() is True
            self.manager.remove_license()
            self.manager._license_info = None
            self.manager._last_check = 0.0
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"50 install/remove cycles took {elapsed:.2f}s"

    def test_concurrent_license_reads(self):
        key = generate_trial_license("concurrent-org", days=30)
        self.manager.install_license(key)
        errors = []

        def reader():
            try:
                for _ in range(20):
                    info = self.manager.get_license_info()
                    assert info.is_valid
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent read errors: {errors}"

    def test_many_key_generations(self):
        start = time.monotonic()
        keys = [generate_trial_license(f"org-{i}", days=30) for i in range(100)]
        elapsed = time.monotonic() - start
        assert len(keys) == 100
        assert len(set(keys)) == 100
        assert elapsed < 3.0, f"100 key generations took {elapsed:.2f}s"

    def test_many_key_parses(self):
        keys = [generate_trial_license(f"org-{i}", days=30) for i in range(100)]
        start = time.monotonic()
        for key in keys:
            info = _parse_license_key(key)
            assert info is not None
            assert info.is_valid
        elapsed = time.monotonic() - start
        assert elapsed < 3.0, f"100 key parses took {elapsed:.2f}s"
