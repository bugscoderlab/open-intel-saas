"""Domain ports for analytics (spec #52 assumption 2).

ApprovedFactsSource is the module's ONLY data path: read-only views of
approved, non-superseded observations plus the service catalog and
locations. The composition root implements it over the
competitor-intelligence unit; tests use their own adapter. Analytics
never imports another business module — dashboards stay available when
collectors or LLMs are down (spec exit condition).
"""

from typing import Protocol, runtime_checkable
from uuid import UUID

from modules.analytics.domain.entities import (
    ApprovedObservation,
    CatalogService,
    CompetitorLocation,
    CompetitorSummary,
    Page,
)


@runtime_checkable
class ApprovedFactsSource(Protocol):
    """Guarded, tenant-scoped reads. Every method takes the row cap and
    reports truncation through Page; implementations apply the statement
    timeout (STATEMENT_TIMEOUT_SECONDS) to each query."""

    async def approved_observations(
        self,
        *,
        project_id: UUID,
        competitor_id: UUID | None = None,
        kinds: frozenset[str] | None = None,
        limit: int,
    ) -> Page[ApprovedObservation]: ...

    async def services(
        self, *, project_id: UUID, limit: int
    ) -> Page[CatalogService]: ...

    async def competitors(
        self,
        *,
        project_id: UUID,
        competitor_ids: tuple[UUID, ...] | None = None,
        limit: int,
    ) -> Page[CompetitorSummary]: ...

    async def locations(
        self,
        *,
        project_id: UUID,
        competitor_id: UUID | None = None,
        limit: int,
    ) -> Page[CompetitorLocation]: ...
