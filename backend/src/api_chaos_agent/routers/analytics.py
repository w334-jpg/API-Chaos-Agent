# Licensed under the Business Source License 1.1 (BSL 1.1)
# See LICENSE.BSL for details. Change Date: 2029-04-30
# Use of this file in production requires a valid commercial license
# unless your organization qualifies under the Additional Use Grant.

"""API routes for analytics and report comparison (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api_chaos_agent.models.analytics import AnalyticsSummary, ComparisonResult, TrendPeriod
from api_chaos_agent.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/v2/analytics", tags=["analytics"])

_service = AnalyticsService()


@router.get("/summary/{tenant_id}", response_model=AnalyticsSummary)
async def get_analytics_summary(tenant_id: str, period: TrendPeriod = TrendPeriod.WEEKLY):
    return _service.get_summary(tenant_id, period)


@router.get("/compare", response_model=ComparisonResult)
async def compare_reports(baseline_report_id: str, comparison_report_id: str):
    from api_chaos_agent.services.store import store

    baseline = await store.get_report(baseline_report_id)
    comparison = await store.get_report(comparison_report_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline report not found")
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison report not found")
    return _service.compare_reports(baseline, comparison)
