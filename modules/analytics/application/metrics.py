"""Metric registry (spec #52 assumption 3): named, unit-bearing
analytical functions over the ApprovedFactsSource port. Definitions are
code — versioned with the module, reviewed like code; there is no
metric-definition table (glossary: Metric definition).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from modules.analytics.domain.entities import ApprovedObservation, MetricResult
from modules.analytics.domain.errors import AnalyticsError

if TYPE_CHECKING:

    from modules.analytics.domain.ports import ApprovedFactsSource

KIND_PRICE = "price"

_ROW_LIMIT = 10_000


@dataclass(frozen=True)
class MetricParams:
    """Competitor scoping for a metric run. None means every competitor
    in the project; ids outside the project are silently excluded by
    the source port (recorded decision on #55)."""

    competitor_ids: tuple[UUID, ...] | None = None


@dataclass(frozen=True)
class Metric:
    name: str
    unit: str
    description: str
    compute: "Callable[[ApprovedFactsSource, UUID, MetricParams], Awaitable[MetricResult]]"


async def _price_trend(
    source: "ApprovedFactsSource", project_id: UUID, params: MetricParams
) -> MetricResult:
    """Approved prices per service over time, observed_on ascending.

    Scoped to the first requested competitor (or the project-wide set
    when none is given — each point still carries its competitor_id).
    """
    competitor_id = params.competitor_ids[0] if params.competitor_ids else None
    page = await source.approved_observations(
        project_id=project_id,
        competitor_id=competitor_id,
        kinds=frozenset({KIND_PRICE}),
        limit=_ROW_LIMIT,
    )
    points = tuple(
        {
            "competitor_id": str(row.competitor_id),
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


async def _competitor_comparison(
    source: "ApprovedFactsSource", project_id: UUID, params: MetricParams
) -> MetricResult:
    """Side-by-side latest approved price per (service, competitor).

    Cells without an approved price are simply absent (the shell renders
    empty cells); competitors outside the project never appear.
    'Latest' = greatest observed_on, ties broken by approval recency
    (created_at desc) — recorded decision on #55.
    """
    competitors = await source.competitors(
        project_id=project_id, competitor_ids=params.competitor_ids, limit=_ROW_LIMIT
    )
    services = await source.services(project_id=project_id, limit=_ROW_LIMIT)
    observations = await source.approved_observations(
        project_id=project_id,
        kinds=frozenset({KIND_PRICE}),
        limit=_ROW_LIMIT,
    )
    wanted = {c.id for c in competitors.rows}
    service_names = {s.id: s.name for s in services.rows}
    competitor_names = {c.id: c.name for c in competitors.rows}

    latest: dict[tuple[UUID, UUID], tuple[date, datetime, ApprovedObservation]] = {}
    for row in observations.rows:
        if row.competitor_id not in wanted or row.service_id is None:
            continue
        key = (row.service_id, row.competitor_id)
        current = latest.get(key)
        if current is None or (row.observed_on, row.created_at) > (
            current[0],
            current[1],
        ):
            latest[key] = (row.observed_on, row.created_at, row)

    points = tuple(
        {
            "service_id": str(service_id),
            "service_name": service_names.get(service_id),
            "competitor_id": str(competitor_id),
            "competitor_name": competitor_names.get(competitor_id),
            "observed_on": chosen.observed_on.isoformat(),
            "price_amount": str(chosen.price_amount) if chosen.price_amount else None,
            "price_currency": chosen.price_currency,
        }
        for (service_id, competitor_id), (_, _, chosen) in sorted(
            latest.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
        )
    )
    return MetricResult(
        metric="competitor_comparison",
        unit="price",
        description="Latest approved price per service per competitor.",
        points=points,
        truncated=competitors.truncated or services.truncated or observations.truncated,
    )


async def _service_coverage(
    source: "ApprovedFactsSource", project_id: UUID, params: MetricParams
) -> MetricResult:
    """Per competitor: how many catalog services carry at least one
    approved observation, with the uncovered names — the review-queue
    workload made visible."""
    competitors = await source.competitors(
        project_id=project_id, competitor_ids=params.competitor_ids, limit=_ROW_LIMIT
    )
    services = await source.services(project_id=project_id, limit=_ROW_LIMIT)
    observations = await source.approved_observations(
        project_id=project_id, limit=_ROW_LIMIT
    )
    service_names = {s.id: s.name for s in services.rows}
    covered_by: dict[UUID, set[UUID]] = {c.id: set() for c in competitors.rows}
    for row in observations.rows:
        if row.service_id is not None and row.service_id in service_names:
            covered_by.setdefault(row.competitor_id, set()).add(row.service_id)

    points = tuple(
        {
            "competitor_id": str(competitor.id),
            "competitor_name": competitor.name,
            "covered": len(covered_by.get(competitor.id, set())),
            "total": len(services.rows),
            "uncovered_service_names": [
                service_names[sid]
                for sid in service_names
                if sid not in covered_by.get(competitor.id, set())
            ],
        }
        for competitor in sorted(competitors.rows, key=lambda c: c.name)
    )
    return MetricResult(
        metric="service_coverage",
        unit="services",
        description="Approved-observation coverage of the service catalog per competitor.",
        points=points,
        truncated=competitors.truncated or services.truncated or observations.truncated,
    )

async def _review_topics(
    source: "ApprovedFactsSource", project_id: UUID, params: MetricParams
) -> MetricResult:
    """Approved review topics per competitor: mention count, dominant
    sentiment (plurality; exact tie -> 'mixed'), latest observation
    date. Topic identity is the observation claim text (#56)."""
    competitor_id = params.competitor_ids[0] if params.competitor_ids else None
    page = await source.approved_observations(
        project_id=project_id,
        competitor_id=competitor_id,
        kinds=frozenset({"review_topic"}),
        limit=_ROW_LIMIT,
    )
    groups: dict[tuple[UUID, str], dict] = {}
    for row in page.rows:
        topic = row.claim or "(unlabeled)"
        key = (row.competitor_id, topic)
        group = groups.setdefault(
            key,
            {"mentions": 0, "sentiments": {}, "latest": row.observed_on},
        )
        group["mentions"] += 1
        if row.sentiment:
            group["sentiments"][row.sentiment] = (
                group["sentiments"].get(row.sentiment, 0) + 1
            )
        if row.observed_on > group["latest"]:
            group["latest"] = row.observed_on

    points = []
    for (competitor, topic), group in sorted(
        groups.items(), key=lambda item: (str(item[0][0]), item[0][1])
    ):
        sentiments = group["sentiments"]
        if not sentiments:
            dominant = None
        else:
            ranked = sorted(sentiments.items(), key=lambda kv: (-kv[1], kv[0]))
            dominant = (
                "mixed"
                if len(ranked) > 1 and ranked[0][1] == ranked[1][1]
                else ranked[0][0]
            )
        points.append(
            {
                "competitor_id": str(competitor),
                "topic": topic,
                "mentions": group["mentions"],
                "dominant_sentiment": dominant,
                "latest_observed_on": group["latest"].isoformat(),
            }
        )
    return MetricResult(
        metric="review_topics",
        unit="mentions",
        description="Approved review topics per competitor with dominant sentiment.",
        points=tuple(points),
        truncated=page.truncated,
    )


async def _location_comparison(
    source: "ApprovedFactsSource", project_id: UUID, params: MetricParams
) -> MetricResult:
    """One competitor's approved facts grouped by location scope: per
    (location, kind) counts + latest values, with a market-level roll-up
    row for NULL-location observations (extraction does not attribute
    locations yet — the roll-up makes that explicit)."""
    competitor_id = params.competitor_ids[0] if params.competitor_ids else None
    locations_page = await source.locations(
        project_id=project_id, competitor_id=competitor_id, limit=_ROW_LIMIT
    )
    observations = await source.approved_observations(
        project_id=project_id,
        competitor_id=competitor_id,
        limit=_ROW_LIMIT,
    )
    location_names = {row.id: row.name for row in locations_page.rows}

    cells: dict[tuple[UUID | None, str], dict] = {}
    for row in observations.rows:
        key = (row.location_id, row.kind)
        cell = cells.setdefault(
            key,
            {
                "count": 0,
                "latest": row.observed_on,
                "price_amount": None,
                "price_currency": None,
            },
        )
        cell["count"] += 1
        if row.observed_on >= cell["latest"]:
            cell["latest"] = row.observed_on
            if row.price_amount is not None:
                cell["price_amount"] = str(row.price_amount)
                cell["price_currency"] = row.price_currency

    points = tuple(
        {
            "location_id": str(location_id) if location_id else None,
            "location_name": (
                location_names.get(location_id) if location_id is not None else None
            ),
            "kind": kind,
            "count": cell["count"],
            "latest_observed_on": cell["latest"].isoformat(),
            "latest_price_amount": cell["price_amount"],
            "latest_price_currency": cell["price_currency"],
        }
        for (location_id, kind), cell in sorted(
            cells.items(), key=lambda item: (str(item[0][0]), item[0][1])
        )
    )
    return MetricResult(
        metric="location_comparison",
        unit="observations",
        description="Approved observations per location scope and kind, with market roll-up.",
        points=points,
        truncated=locations_page.truncated or observations.truncated,
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
        Metric(
            name="competitor_comparison",
            unit="price",
            description="Latest approved price per service per competitor.",
            compute=_competitor_comparison,
        ),
        Metric(
            name="service_coverage",
            unit="services",
            description="Coverage of the service catalog per competitor.",
            compute=_service_coverage,
        ),
        Metric(
            name="review_topics",
            unit="mentions",
            description="Approved review topics per competitor with dominant sentiment.",
            compute=_review_topics,
        ),
        Metric(
            name="location_comparison",
            unit="observations",
            description="Approved observations per location scope and kind.",
            compute=_location_comparison,
        ),
    )
}


def get_metric(name: str) -> Metric:
    try:
        return METRICS[name]
    except KeyError as exc:
        raise AnalyticsError(f"unknown metric {name!r}") from exc
