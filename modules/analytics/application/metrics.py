"""Metric registry (spec #52 assumption 3): named, unit-bearing
analytical functions over the ApprovedFactsSource port. Definitions are
code — versioned with the module, reviewed like code; there is no
metric-definition table (glossary: Metric definition).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from modules.analytics.domain.entities import MetricResult
from modules.analytics.domain.errors import AnalyticsError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from modules.analytics.domain.ports import ApprovedFactsSource

KIND_PRICE = "price"


@dataclass(frozen=True)
class Metric:
    name: str
    unit: str
    description: str
    compute: "Callable[[ApprovedFactsSource, UUID, UUID], Awaitable[MetricResult]]"


async def _price_trend(
    source: "ApprovedFactsSource", project_id: UUID, competitor_id: UUID
) -> MetricResult:
    """Approved prices per service over time, observed_on ascending.

    Grain is (service, observed_on) with one point per approved
    observation row — superseded rows never reach the source port
    (spec #54 assumption). Mixed currencies are returned as-is (no FX).
    """
    page = await source.approved_observations(
        project_id=project_id,
        competitor_id=competitor_id,
        kinds=frozenset({KIND_PRICE}),
        limit=10_000,
    )
    points = tuple(
        {
            "service_id": str(row.service_id) if row.service_id else None,
            "observed_on": row.observed_on.isoformat(),
            "price_amount": str(row.price_amount) if row.price_amount else None,
            "price_currency": row.price_currency,
        }
        for row in sorted(page.rows, key=lambda r: (r.observed_on, r.id))
    )
    return MetricResult(
        metric="price_trend",
        unit="price",
        description="Approved prices per service over time, observed_on ascending.",
        points=points,
        truncated=page.truncated,
    )


# The registry: metrics are looked up by name for both the JSON
# endpoints and CSV export (spec #57 reuses these functions).
METRICS: dict[str, Metric] = {
    metric.name: metric
    for metric in (
        Metric(
            name="price_trend",
            unit="price",
            description="Approved prices per service over time.",
            compute=_price_trend,
        ),
    )
}


def get_metric(name: str) -> Metric:
    try:
        return METRICS[name]
    except KeyError as exc:
        raise AnalyticsError(f"unknown metric {name!r}") from exc
