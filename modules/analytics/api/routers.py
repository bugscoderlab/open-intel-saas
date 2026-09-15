"""HTTP routers for the analytics module (tickets #54/#55, spec #52).

Thin router: parse, authorize behind the matrix, run the named metric
over the ApprovedFactsSource port, map typed errors to statuses.
Analytics is read-only — every endpoint is a GET.
"""

from uuid import UUID

from fastapi import APIRouter, Query

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
        result = await analytics_service.run_metric(
            unit,
            authz,
            principal,
            source,
            metric_name="price_trend",
            project_id=project_id,
            competitor_ids=(competitor_id,),
        )
        return _metric_response(result)

    @router.get(
        "/projects/{project_id}/analytics/comparison",
        response_model=MetricResponse,
    )
    @endpoint
    async def competitor_comparison(
        project_id: UUID,
        unit: AnalyticsUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        source: FactsSourceDep,
        competitor_ids: list[UUID] = Query(default=[]),
    ) -> MetricResponse:
        # Omitted filter = every competitor in the project; ids outside
        # the project are silently excluded by the source port (#55).
        result = await analytics_service.run_metric(
            unit,
            authz,
            principal,
            source,
            metric_name="competitor_comparison",
            project_id=project_id,
            competitor_ids=tuple(competitor_ids) or None,
        )
        return _metric_response(result)

    @router.get(
        "/projects/{project_id}/analytics/service-coverage",
        response_model=MetricResponse,
    )
    @endpoint
    async def service_coverage(
        project_id: UUID,
        unit: AnalyticsUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        source: FactsSourceDep,
        competitor_ids: list[UUID] = Query(default=[]),
    ) -> MetricResponse:
        result = await analytics_service.run_metric(
            unit,
            authz,
            principal,
            source,
            metric_name="service_coverage",
            project_id=project_id,
            competitor_ids=tuple(competitor_ids) or None,
        )
        return _metric_response(result)

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}"
        "/analytics/review-topics",
        response_model=MetricResponse,
    )
    @endpoint
    async def review_topics(
        project_id: UUID,
        competitor_id: UUID,
        unit: AnalyticsUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        source: FactsSourceDep,
    ) -> MetricResponse:
        result = await analytics_service.run_metric(
            unit,
            authz,
            principal,
            source,
            metric_name="review_topics",
            project_id=project_id,
            competitor_ids=(competitor_id,),
        )
        return _metric_response(result)

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}"
        "/analytics/locations",
        response_model=MetricResponse,
    )
    @endpoint
    async def location_comparison(
        project_id: UUID,
        competitor_id: UUID,
        unit: AnalyticsUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        source: FactsSourceDep,
    ) -> MetricResponse:
        result = await analytics_service.run_metric(
            unit,
            authz,
            principal,
            source,
            metric_name="location_comparison",
            project_id=project_id,
            competitor_ids=(competitor_id,),
        )
        return _metric_response(result)

    return router
