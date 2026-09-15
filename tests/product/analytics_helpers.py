"""Test-side implementation of the analytics ApprovedFactsSource port
(ticket #54) — the same guarded read path as the serve.py composition
root, built over the test engine with a configurable row cap so the
truncation guardrail is testable without 10k rows.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.analytics.domain.entities import (
    DEFAULT_ROW_CAP,
    STATEMENT_TIMEOUT_SECONDS,
    ApprovedObservation,
    CatalogService,
    CompetitorLocation,
    CompetitorSummary,
    Page,
)


class TestApprovedFactsSource:
    """Read-only views over competitor-intelligence tables: approved,
    non-superseded observations plus the service catalog and locations.
    Every query carries tenant scope (project_id), a statement timeout,
    and a row cap detected by fetching limit+1."""

    def __init__(self, engine: AsyncEngine, *, row_cap: int = DEFAULT_ROW_CAP) -> None:
        self._engine = engine
        self.row_cap = row_cap

    async def _query(self, stmt, *, limit: int):
        from sqlalchemy import text

        from modules.competitor_intelligence.infrastructure.unit_of_work import (
            SqlCompetitorUnit,
        )

        capped = min(limit, self.row_cap)
        async with SqlCompetitorUnit(self._engine) as unit:
            assert unit._session is not None
            # Guardrails (spec #52 assumption 5): transaction-scoped
            # statement timeout + the row cap (limit+1 detects the cut).
            await unit._session.execute(  # noqa: SLF001
                # Constant integer — SET LOCAL takes no bind parameters.
                text(
                    f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_SECONDS * 1000}"
                )
            )
            result = await unit._session.execute(  # noqa: SLF001
                stmt.limit(capped + 1)
            )
            rows = result.all()
        return rows[:capped], len(rows) > capped

    async def approved_observations(
        self,
        *,
        project_id: UUID,
        competitor_id: UUID | None = None,
        kinds: frozenset[str] | None = None,
        limit: int = DEFAULT_ROW_CAP,
    ) -> Page[ApprovedObservation]:
        from modules.competitor_intelligence.infrastructure.db import (
            observations as observations_table,
        )

        stmt = select(observations_table).where(
            observations_table.c.project_id == project_id,
            observations_table.c.approval_state == "approved",
            observations_table.c.superseded_by.is_(None),
        )
        if competitor_id is not None:
            stmt = stmt.where(observations_table.c.competitor_id == competitor_id)
        if kinds is not None:
            stmt = stmt.where(observations_table.c.kind.in_(kinds))
        rows, truncated = await self._query(stmt.order_by(observations_table.c.observed_on), limit=limit)
        return Page(
            rows=tuple(
                ApprovedObservation(
                    id=row.id,
                    competitor_id=row.competitor_id,
                    service_id=row.service_id,
                    location_id=row.location_id,
                    kind=row.kind,
                    price_amount=row.price_amount,
                    price_currency=row.price_currency,
                    observed_on=row.observed_on,
                    superseded_by=row.superseded_by,
                    created_at=row.created_at,
                )
                for row in rows
            ),
            truncated=truncated,
        )

    async def services(
        self, *, project_id: UUID, limit: int = DEFAULT_ROW_CAP
    ) -> Page[CatalogService]:
        from modules.competitor_intelligence.infrastructure.db import (
            services as services_table,
        )

        stmt = select(services_table).where(services_table.c.project_id == project_id)
        rows, truncated = await self._query(stmt, limit=limit)
        return Page(
            rows=tuple(
                CatalogService(id=row.id, project_id=row.project_id, name=row.name)
                for row in rows
            ),
            truncated=truncated,
        )

    async def competitors(
        self,
        *,
        project_id,
        competitor_ids=None,
        limit: int = DEFAULT_ROW_CAP,
    ) -> Page[CompetitorSummary]:
        from modules.competitor_intelligence.infrastructure.db import (
            competitors as competitors_table,
        )

        stmt = select(competitors_table).where(
            competitors_table.c.project_id == project_id
        )
        if competitor_ids is not None:
            stmt = stmt.where(competitors_table.c.id.in_(competitor_ids))
        rows, truncated = await self._query(stmt, limit=limit)
        return Page(
            rows=tuple(
                CompetitorSummary(
                    id=row.id, project_id=row.project_id, name=row.name
                )
                for row in rows
            ),
            truncated=truncated,
        )

    async def locations(
        self,
        *,
        project_id: UUID,
        competitor_id: UUID | None = None,
        limit: int = DEFAULT_ROW_CAP,
    ) -> Page[CompetitorLocation]:
        from modules.competitor_intelligence.infrastructure.db import (
            locations as locations_table,
        )

        stmt = select(locations_table).where(
            locations_table.c.project_id == project_id
        )
        if competitor_id is not None:
            stmt = stmt.where(locations_table.c.competitor_id == competitor_id)
        rows, truncated = await self._query(stmt, limit=limit)
        return Page(
            rows=tuple(
                CompetitorLocation(
                    id=row.id,
                    project_id=row.project_id,
                    competitor_id=row.competitor_id,
                    name=row.name,
                )
                for row in rows
            ),
            truncated=truncated,
        )


__all__ = ["TestApprovedFactsSource", "STATEMENT_TIMEOUT_SECONDS"]
