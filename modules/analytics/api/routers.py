"""HTTP routers for the analytics module (ticket #54, spec #52).

Thin router: parse, authorize behind the matrix, run the named metric
over the ApprovedFactsSource port, map typed errors to statuses.
Analytics is read-only — every endpoint is a GET.
"""

from uuid import UUID

from fastapi import APIRouter

from modules.analytics.api.deps import (
    AnalyticsUnitDep,
    AuthzDep,
    FactsSourceDep,
    PrincipalDep,
)
from modules.analytics.api.schemas import MetricResponse
from modules.analytics.application.services import analytics_service
from modules.analytics.domain.entities import MetricResult
from modules.platform.api.routers import endpoint


def _metric_response(result: MetricResult) -> MetricResponse:
    return MetricResponse(
        metric=result.metric,
        unit=result.unit,
        description=result.description,
        points=list(result.points),
        truncated=result.truncated,
    )


def build_analytics_router() -> APIRouter:
    router = APIRouter(tags=["analytics"])

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}/analytics/price-trend",
        response_model=MetricResponse,
    )
    @endpoint
    async def price_trend(
        project_id: UUID,
        competitor_id: UUID,
        unit: AnalyticsUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        source: FactsSourceDep,
    ) -> MetricResponse:
        result = await analytics_service.run_metric_for_competitor(
            unit,
            authz,
            principal,
            source,
            metric_name="price_trend",
            project_id=project_id,
            competitor_id=competitor_id,
        )
        return _metric_response(result)

    return router
