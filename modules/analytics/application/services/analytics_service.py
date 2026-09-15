"""Analytics use cases (ticket #54, spec #52): run one named metric for
a competitor, behind the matrix and tenant scope. Read-only — no audit
on reads, matching the existing read endpoints (snapshots list,
observations list).
"""

from uuid import UUID

from modules.analytics.application.metrics import get_metric
from modules.analytics.domain.entities import MetricResult
from modules.analytics.domain.errors import AnalyticsQueryError
from modules.analytics.domain.ports import ApprovedFactsSource
from modules.analytics.domain.unit_of_work import AnalyticsUnit
from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def run_metric_for_competitor(
    unit: AnalyticsUnit,
    authz: AuthorizationService,
    principal: Principal,
    source: ApprovedFactsSource,
    *,
    metric_name: str,
    project_id: UUID,
    competitor_id: UUID,
) -> MetricResult:
    """analytics.read — execute one registered metric. The project load
    enforces tenant scope; the source port re-carries project_id on
    every query underneath."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.ANALYTICS_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    metric = get_metric(metric_name)
    try:
        result = await metric.compute(source, project_id, competitor_id)
    except AnalyticsQueryError:
        raise
    except Exception as exc:  # noqa: BLE001 — the metric boundary types
        # unexpected port failures instead of leaking bare exceptions.
        raise AnalyticsQueryError(f"metric {metric.name!r} failed: {exc}") from exc
    assert isinstance(result, MetricResult)
    return result
