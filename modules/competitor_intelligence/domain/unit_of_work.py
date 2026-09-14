"""The competitor-intelligence unit of work: the platform's repositories
plus this module's own, in one transaction (mirrors ResearchUnit).

Competitors requires Platform only (plan §14.3): research is an optional
dependency, so this unit extends PlatformUnit — never ResearchUnit — and
cross-module references (evidence targets) stay opaque UUIDs.
"""

from typing import Protocol
from uuid import UUID

from modules.competitor_intelligence.domain.entities import Competitor, Location
from modules.platform.domain.unit_of_work import PlatformUnit


class Competitors(Protocol):
    """Competitor repository — the tenant scope is explicit on every
    query, mirroring the research contract."""

    async def create(self, competitor: Competitor) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> Competitor | None: ...
    async def update(self, competitor: Competitor) -> None: ...
    async def delete(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> None: ...
    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Competitor]: ...


class Locations(Protocol):
    """Location repository — scoped through the owning competitor."""

    async def create(self, location: Location) -> None: ...
    async def get(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
    ) -> Location | None: ...
    async def update(self, location: Location) -> None: ...
    async def delete(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
    ) -> None: ...
    async def list_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> list[Location]: ...


class CompetitorUnit(PlatformUnit, Protocol):
    """One transaction worth of platform + competitor repositories."""

    competitors: Competitors
    locations: Locations
