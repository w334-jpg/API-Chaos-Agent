"""API routes for analytics and report comparison (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter

from api_chaos_agent.core.exceptions import NotFoundError

from api_chaos_agent.core.deps import AnalyticsServiceDep, StoreDep
from api_chaos_agent.models.analytics import AnalyticsSummary, ComparisonResult, TrendPeriod

router = APIRouter(prefix="/api/v2/analytics", tags=["analytics"])


@router.get("/summary/{tenant_id}", response_model=AnalyticsSummary)
async def get_analytics_summary(
    service: AnalyticsServiceDep,
    tenant_id: str,
    period: TrendPeriod = TrendPeriod.WEEKLY,
):
    return service.get_summary(tenant_id, period)


@router.get("/compare", response_model=ComparisonResult)
async def compare_reports(
    service: AnalyticsServiceDep,
    store: StoreDep,
    baseline_report_id: str,
    comparison_report_id: str,
):
    baseline = await store.get_report(baseline_report_id)
    comparison = await store.get_report(comparison_report_id)
    if not baseline:
        raise NotFoundError(detail="Baseline report not found")
    if not comparison:
        raise NotFoundError(detail="Comparison report not found")
    return service.compare_reports(baseline, comparison)
