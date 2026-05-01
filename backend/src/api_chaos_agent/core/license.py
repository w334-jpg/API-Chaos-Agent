"""License management for API Chaos Agent.

Handles BSL 1.1 compliance, commercial license verification,
trial license generation, and feature gating based on license tier.

Licensed under the Business Source License 1.1 (BSL 1.1).
See LICENSE.BSL for details. Change Date: 2029-04-30.
Use of this file in production requires a valid commercial license
unless your organization qualifies under the Additional Use Grant.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.tenant import TenantPlan

logger = get_logger(__name__)

BSL_HEADER = (
    "# Licensed under the Business Source License 1.1 (BSL 1.1)\n"
    "# See LICENSE.BSL for details. Change Date: 2029-04-30\n"
    "# Use of this file in production requires a valid commercial license\n"
    "# unless your organization qualifies under the Additional Use Grant.\n"
)

BSL_PROTECTED_MODULES = frozenset(
    {
        "api_chaos_agent.services.grpc_graphql_parser",
        "api_chaos_agent.services.distributed_engine",
        "api_chaos_agent.services.plugin_framework",
        "api_chaos_agent.services.cicd_service",
        "api_chaos_agent.services.tenant_service",
        "api_chaos_agent.services.analytics_service",
        "api_chaos_agent.models.analytics",
        "api_chaos_agent.models.cicd",
        "api_chaos_agent.models.distributed",
        "api_chaos_agent.models.plugin",
        "api_chaos_agent.models.tenant",
        "api_chaos_agent.routers.schemas_v2",
        "api_chaos_agent.routers.distributed",
        "api_chaos_agent.routers.plugins",
        "api_chaos_agent.routers.cicd",
        "api_chaos_agent.routers.tenants",
        "api_chaos_agent.routers.analytics",
        "api_chaos_agent.routers.plans",
        "api_chaos_agent.core.feature_gates",
    }
)


class LicenseType(StrEnum):
    BSL = "bsl"
    COMMERCIAL_PRO = "commercial_pro"
    COMMERCIAL_ENTERPRISE = "commercial_enterprise"
    TRIAL = "trial"


class LicenseStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    MISSING = "missing"
    BSL_NON_PRODUCTION = "bsl_non_production"


class LicenseInfo(BaseModel):
    license_type: LicenseType = LicenseType.BSL
    status: LicenseStatus = LicenseStatus.BSL_NON_PRODUCTION
    holder: str = ""
    plan: TenantPlan = TenantPlan.FREE
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    features: list[str] = Field(default_factory=list)
    max_seats: int = 1
    is_production: bool = False

    @property
    def is_valid(self) -> bool:
        return self.status in (LicenseStatus.VALID, LicenseStatus.BSL_NON_PRODUCTION)

    @property
    def is_commercial(self) -> bool:
        return self.license_type in (
            LicenseType.COMMERCIAL_PRO,
            LicenseType.COMMERCIAL_ENTERPRISE,
            LicenseType.TRIAL,
        )

    @property
    def days_until_expiry(self) -> int | None:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now()
        return max(0, delta.days)


_LICENSE_SECRET = os.environ.get(
    "API_CHAOS_AGENT_LICENSE_SECRET",
    "api-chaos-agent-license-verification-key-v2",
)

_LICENSE_FILE_PATHS = [
    Path("license.key"),
    Path.home() / ".api-chaos-agent" / "license.key",
    Path("/etc/api-chaos-agent/license.key"),
]


def _verify_signature(payload: str, signature: str) -> bool:
    expected = hmac.new(_LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _generate_signature(payload: str) -> str:
    return hmac.new(_LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _read_license_file() -> str | None:
    env_path = os.environ.get("API_CHAOS_AGENT_LICENSE_FILE")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p.read_text().strip()
    for path in _LICENSE_FILE_PATHS:
        if path.exists():
            return path.read_text().strip()
    return None


def _parse_license_key(key: str) -> LicenseInfo | None:
    try:
        parts = key.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature = parts
        import base64

        payload_json = base64.urlsafe_b64decode(payload_b64 + "==")
        payload = json.loads(payload_json)
        if not _verify_signature(payload_b64, signature):
            logger.warning("license_signature_invalid")
            return None
        expires_at = (
            datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
        )
        if expires_at and datetime.now() > expires_at:
            return LicenseInfo(
                license_type=LicenseType(payload.get("type", "bsl")),
                status=LicenseStatus.EXPIRED,
                holder=payload.get("holder", ""),
                plan=TenantPlan(payload.get("plan", "free")),
                issued_at=datetime.fromisoformat(payload["issued_at"])
                if payload.get("issued_at")
                else None,
                expires_at=expires_at,
                features=payload.get("features", []),
                max_seats=payload.get("max_seats", 1),
                is_production=payload.get("is_production", False),
            )
        return LicenseInfo(
            license_type=LicenseType(payload.get("type", "bsl")),
            status=LicenseStatus.VALID,
            holder=payload.get("holder", ""),
            plan=TenantPlan(payload.get("plan", "free")),
            issued_at=datetime.fromisoformat(payload["issued_at"])
            if payload.get("issued_at")
            else None,
            expires_at=expires_at,
            features=payload.get("features", []),
            max_seats=payload.get("max_seats", 1),
            is_production=payload.get("is_production", False),
        )
    except Exception as e:
        logger.warning("license_parse_failed", error=str(e))
        return None


def _is_production_environment() -> bool:
    env = os.environ.get("API_CHAOS_AGENT_ENV", os.environ.get("NODE_ENV", "development"))
    return env.lower() in ("production", "prod", "staging", "stage")


def _check_bsl_eligibility() -> bool:
    org_size = int(os.environ.get("API_CHAOS_AGENT_ORG_SIZE", "0"))
    org_revenue = float(os.environ.get("API_CHAOS_AGENT_ORG_REVENUE", "0"))
    if org_size > 0 and org_size < 50 and org_revenue < 1_000_000:
        return True
    nonprofit = os.environ.get("API_CHAOS_AGENT_NONPROFIT", "").lower()
    if nonprofit in ("true", "1", "yes"):
        return True
    academic = os.environ.get("API_CHAOS_AGENT_ACADEMIC", "").lower()
    if academic in ("true", "1", "yes"):
        return True
    return False


class LicenseManager:
    _instance: LicenseManager | None = None
    _license_info: LicenseInfo | None = None
    _last_check: float = 0.0
    _check_interval: float = 3600.0

    def __new__(cls) -> LicenseManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_license_info(self) -> LicenseInfo:
        now = time.monotonic()
        if self._license_info and (now - self._last_check) < self._check_interval:
            return self._license_info

        key = _read_license_file()
        if key:
            info = _parse_license_key(key)
            if info and info.is_valid:
                self._license_info = info
                self._last_check = now
                return info
            if info and info.status == LicenseStatus.EXPIRED:
                logger.warning(
                    "license_expired", holder=info.holder, expires_at=str(info.expires_at)
                )
                self._license_info = info
                self._last_check = now
                return info

        is_prod = _is_production_environment()
        if is_prod and not _check_bsl_eligibility():
            self._license_info = LicenseInfo(
                license_type=LicenseType.BSL,
                status=LicenseStatus.BSL_NON_PRODUCTION,
                is_production=True,
            )
        else:
            self._license_info = LicenseInfo(
                license_type=LicenseType.BSL,
                status=LicenseStatus.BSL_NON_PRODUCTION,
                is_production=is_prod,
            )
        self._last_check = now
        return self._license_info

    def can_use_pro_features(self) -> bool:
        info = self.get_license_info()
        if info.is_commercial and info.is_valid:
            return info.plan in (TenantPlan.PRO, TenantPlan.ENTERPRISE)
        if info.status == LicenseStatus.BSL_NON_PRODUCTION:
            if not _is_production_environment():
                return True
            return _check_bsl_eligibility()
        return False

    def can_use_enterprise_features(self) -> bool:
        info = self.get_license_info()
        if info.is_commercial and info.is_valid:
            return info.plan == TenantPlan.ENTERPRISE
        return False

    def require_pro(self) -> None:
        if not self.can_use_pro_features():
            from api_chaos_agent.core.exceptions import SecurityError

            raise SecurityError(
                detail="This feature requires a Professional or Enterprise license. "
                "Visit /pricing for details or contact license@api-chaos-agent.dev",
            )

    def require_enterprise(self) -> None:
        if not self.can_use_enterprise_features():
            from api_chaos_agent.core.exceptions import SecurityError

            raise SecurityError(
                detail="This feature requires an Enterprise license. "
                "Contact license@api-chaos-agent.dev for pricing.",
            )

    def install_license(self, key: str) -> LicenseInfo:
        info = _parse_license_key(key)
        if not info or not info.is_valid:
            raise ValueError("Invalid license key")
        try:
            license_dir = Path.home() / ".api-chaos-agent"
            license_dir.mkdir(parents=True, exist_ok=True)
            license_path = license_dir / "license.key"
            license_path.write_text(key)
        except (PermissionError, OSError) as exc:
            logger.warning("license_file_write_failed", error=str(exc), path=str(license_path))
        self._license_info = info
        self._last_check = time.monotonic()
        logger.info("license_installed", type=info.license_type.value, plan=info.plan.value)
        return info

    def remove_license(self) -> bool:
        for path in _LICENSE_FILE_PATHS:
            if path.exists():
                path.unlink()
        self._license_info = None
        self._last_check = 0.0
        return True


license_manager = LicenseManager()


def generate_trial_license(holder: str, days: int = 30) -> str:
    import base64

    now = datetime.now()
    expires = now + timedelta(days=days)
    payload = {
        "type": "trial",
        "holder": holder,
        "plan": "pro",
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "features": [
            "distributed_execution",
            "custom_plugins",
            "cicd_integration",
            "advanced_analytics",
            "graphql_support",
            "grpc_support",
            "team_collaboration",
            "api_key_management",
        ],
        "max_seats": 5,
        "is_production": True,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    signature = _generate_signature(payload_b64)
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"sha256","typ":"license"}').rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{signature}"
