"""The competitor-intelligence unit of work: the platform's repositories
plus this module's own, in one transaction (mirrors ResearchUnit).

Competitors requires Platform only (plan §14.3): research is an optional
dependency, so this unit extends PlatformUnit — never ResearchUnit — and
cross-module references (evidence targets) stay opaque UUIDs.
"""

from typing import Protocol
from uuid import UUID

from modules.competitor_intelligence.domain.entities import (
    Competitor,
    Location,
    Observation,
    Service,
)
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


class Services(Protocol):
    """Service catalog repository — the tenant scope is explicit on every
    query; names dedupe case-insensitively per project."""

    async def create(self, service: Service) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, service_id: UUID
    ) -> Service | None: ...
    async def get_by_name(
        self, organization_id: UUID, project_id: UUID, name: str
    ) -> Service | None: ...
    async def delete(
        self, organization_id: UUID, project_id: UUID, service_id: UUID
    ) -> None: ...
    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Service]: ...


class Observations(Protocol):
    """Observation repository — stored, never overwritten (glossary):
    the only in-place update is the approval-state flip."""

    async def create(self, observation: Observation) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, observation_id: UUID
    ) -> Observation | None: ...
    async def update_state(
        self,
        organization_id: UUID,
        project_id: UUID,
        observation_id: UUID,
        *,
        approval_state: str,
        superseded_by: UUID | None,
    ) -> None: ...
    async def list_pending_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Observation]: ...
    async def list_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> list[Observation]: ...
    async def list_approved_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID, kind: str
    ) -> list[Observation]: ...
    async def count_referencing_service(
        self, organization_id: UUID, project_id: UUID, service_id: UUID
    ) -> int: ...


class CompetitorUnit(PlatformUnit, Protocol):
    """One transaction worth of platform + competitor repositories."""

    competitors: Competitors
    locations: Locations
    services: Services
    observations: Observations
