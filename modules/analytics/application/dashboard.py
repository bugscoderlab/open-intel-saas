"""Dashboard assembly (ticket #57): one roundtrip payload with the
per-competitor widget sections the workspace overview renders, plus the
recent-Changes section (Signals feed). Widgets stay data-only — the
shell owns presentation (glossary: Dashboard widget).
"""

from uuid import UUID

from modules.analytics.application.metrics import (
    MetricParams,
    _competitor_comparison,
    _price_trend,
    _review_topics,
    _service_coverage,
)
from modules.analytics.domain.ports import ApprovedFactsSource


async def build_dashboard(
    source: ApprovedFactsSource,
    *,
    project_id: UUID,
    competitor_ids: tuple[UUID, ...] | None,
) -> dict:
    """Assemble the widget payload. Sections reuse the registered metric
    functions so dashboard numbers can never drift from the endpoints;
    changes come from the superseded rows (durable Change read model)."""
    params = MetricParams(competitor_ids=competitor_ids)
    trend = await _price_trend(source, project_id, params)
    comparison = await _competitor_comparison(source, project_id, params)
    coverage = await _service_coverage(source, project_id, params)
    topics = await _review_topics(source, project_id, params)
    changes_page = await source.superseded_observations(
        project_id=project_id,
        competitor_ids=competitor_ids,
        limit=100,
    )

    competitors = sorted(
        {p["competitor_id"] for p in comparison.points}
        | {p["competitor_id"] for p in coverage.points}
        | {p["competitor_id"] for p in topics.points}
        | {str(row.competitor_id) for row in changes_page.rows}
    )
    sections = []
    for competitor in competitors:
        sections.append(
            {
                "competitor_id": competitor,
                "price_trend": [
                    p for p in trend.points if p["competitor_id"] == competitor
                ],
                "comparison": [
                    p for p in comparison.points if p["competitor_id"] == competitor
                ],
                "service_coverage": next(
                    (
                        p
                        for p in coverage.points
                        if p["competitor_id"] == competitor
                    ),
                    None,
                ),
                "review_topics": [
                    p for p in topics.points if p["competitor_id"] == competitor
                ],
                "changes": [
                    {
                        "observation_id": str(row.id),
                        "kind": row.kind,
                        "claim": row.claim,
                        "price_amount": (
                            str(row.price_amount) if row.price_amount else None
                        ),
                        "price_currency": row.price_currency,
                        "observed_on": row.observed_on.isoformat(),
                        "superseded_by": str(row.superseded_by),
                    }
                    for row in changes_page.rows
                    if str(row.competitor_id) == competitor
                ],
            }
        )
    return {
        "project_id": str(project_id),
        "competitors": sections,
        "truncated": any(
            (
                trend.truncated,
                comparison.truncated,
                coverage.truncated,
                topics.truncated,
                changes_page.truncated,
            )
        ),
    }
