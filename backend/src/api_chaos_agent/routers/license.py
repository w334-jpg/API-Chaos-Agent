from __future__ import annotations

from fastapi import APIRouter

from api_chaos_agent.core.exceptions import LicenseError as LicenseExc

from api_chaos_agent.core.license import LicenseInfo, license_manager

router = APIRouter(prefix="/license", tags=["license"])


@router.get("/info", response_model=LicenseInfo)
async def get_license_info():
    return license_manager.get_license_info()


@router.post("/install")
async def install_license(key: str):
    try:
        info = license_manager.install_license(key)
        return info
    except ValueError as e:
        raise LicenseExc(detail=str(e))


@router.delete("/remove")
async def remove_license():
    license_manager.remove_license()
    return {"status": "removed"}


@router.get("/check-pro")
async def check_pro_access():
    return {"can_use_pro": license_manager.can_use_pro_features()}


@router.get("/check-enterprise")
async def check_enterprise_access():
    return {"can_use_enterprise": license_manager.can_use_enterprise_features()}
