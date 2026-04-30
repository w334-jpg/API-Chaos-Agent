"""Unit tests for BSL License Manager."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api_chaos_agent.core.license import (
    LicenseInfo,
    LicenseManager,
    LicenseStatus,
    LicenseType,
    generate_trial_license,
    license_manager,
)
from api_chaos_agent.models.tenant import TenantPlan


class TestLicenseInfo:
    def test_bsl_default(self):
        info = LicenseInfo()
        assert info.license_type == LicenseType.BSL
        assert info.status == LicenseStatus.BSL_NON_PRODUCTION
        assert not info.is_commercial
        assert info.is_valid

    def test_commercial_pro(self):
        info = LicenseInfo(
            license_type=LicenseType.COMMERCIAL_PRO,
            status=LicenseStatus.VALID,
            plan=TenantPlan.PRO,
            is_production=True,
        )
        assert info.is_commercial
        assert info.is_valid

    def test_expired_license(self):
        info = LicenseInfo(
            license_type=LicenseType.COMMERCIAL_PRO,
            status=LicenseStatus.EXPIRED,
            plan=TenantPlan.PRO,
            expires_at=datetime.now() - timedelta(days=1),
        )
        assert not info.is_valid
        assert info.days_until_expiry == 0

    def test_days_until_expiry(self):
        info = LicenseInfo(
            license_type=LicenseType.COMMERCIAL_PRO,
            status=LicenseStatus.VALID,
            expires_at=datetime.now() + timedelta(days=30),
        )
        assert info.days_until_expiry is not None
        assert 29 <= info.days_until_expiry <= 31

    def test_no_expiry(self):
        info = LicenseInfo()
        assert info.days_until_expiry is None


class TestTrialLicenseGeneration:
    def test_generate_trial(self):
        key = generate_trial_license("test-user", days=30)
        assert isinstance(key, str)
        parts = key.split(".")
        assert len(parts) == 3

    def test_trial_key_parseable(self):
        key = generate_trial_license("test-user", days=30)
        import base64
        import json
        parts = key.split(".")
        payload_json = base64.urlsafe_b64decode(parts[1] + "==")
        payload = json.loads(payload_json)
        assert payload["type"] == "trial"
        assert payload["holder"] == "test-user"
        assert payload["plan"] == "pro"


class TestLicenseManager:
    def setup_method(self):
        self.manager = LicenseManager()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        for path in [Path("license.key"), Path.home() / ".api-chaos-agent" / "license.key"]:
            if path.exists():
                path.unlink()
        os.environ.pop("API_CHAOS_AGENT_LICENSE_FILE", None)

    def test_default_bsl_in_dev(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        info = self.manager.get_license_info()
        assert info.license_type == LicenseType.BSL
        assert info.status == LicenseStatus.BSL_NON_PRODUCTION

    def test_can_use_pro_in_dev(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        assert self.manager.can_use_pro_features()

    def test_cannot_use_enterprise_without_license(self):
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        assert not self.manager.can_use_enterprise_features()

    def test_install_trial_license(self):
        key = generate_trial_license("test-org", days=30)
        info = self.manager.install_license(key)
        assert info.license_type == LicenseType.TRIAL
        assert info.status == LicenseStatus.VALID
        assert info.plan == TenantPlan.PRO
        assert self.manager.can_use_pro_features()

    def test_install_invalid_key(self):
        with pytest.raises(ValueError, match="Invalid license key"):
            self.manager.install_license("invalid.key.format")

    def test_remove_license(self):
        key = generate_trial_license("test-org", days=30)
        self.manager.install_license(key)
        assert self.manager.can_use_pro_features()
        self.manager.remove_license()
        self.manager._license_info = None
        self.manager._last_check = 0.0
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("NODE_ENV", None)
        assert self.manager.can_use_pro_features()

    def test_production_env_without_bsl_eligibility(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ.pop("API_CHAOS_AGENT_ORG_SIZE", None)
        os.environ.pop("API_CHAOS_AGENT_NONPROFIT", None)
        os.environ.pop("API_CHAOS_AGENT_ACADEMIC", None)
        self.manager._license_info = None
        self.manager._last_check = 0.0
        info = self.manager.get_license_info()
        assert info.is_production
        os.environ.pop("API_CHAOS_AGENT_ENV", None)

    def test_small_org_bsl_eligible(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ORG_SIZE"] = "10"
        os.environ["API_CHAOS_AGENT_ORG_REVENUE"] = "500000"
        self.manager._license_info = None
        self.manager._last_check = 0.0
        assert self.manager.can_use_pro_features()
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("API_CHAOS_AGENT_ORG_SIZE", None)
        os.environ.pop("API_CHAOS_AGENT_ORG_REVENUE", None)

    def test_nonprofit_bsl_eligible(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_NONPROFIT"] = "true"
        self.manager._license_info = None
        self.manager._last_check = 0.0
        assert self.manager.can_use_pro_features()
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("API_CHAOS_AGENT_NONPROFIT", None)

    def test_academic_bsl_eligible(self):
        os.environ["API_CHAOS_AGENT_ENV"] = "production"
        os.environ["API_CHAOS_AGENT_ACADEMIC"] = "true"
        self.manager._license_info = None
        self.manager._last_check = 0.0
        assert self.manager.can_use_pro_features()
        os.environ.pop("API_CHAOS_AGENT_ENV", None)
        os.environ.pop("API_CHAOS_AGENT_ACADEMIC", None)
