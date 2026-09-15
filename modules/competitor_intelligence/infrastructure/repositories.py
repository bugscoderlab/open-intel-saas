"""SQLAlchemy implementations of the competitor repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (mirrors the platform and
research contracts, plan §8.2).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.competitor_intelligence.domain.entities import (
    Competitor,
    EvidenceLink,
    Location,
    Observation,
    Service,
)
from modules.competitor_intelligence.infrastructure import db as tables


def _row_to_competitor(row: Row) -> Competitor:
    return Competitor(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        name=row.name,
        website=row.website,
        notes=row.notes,
        created_by=row.created_by,
    )


class SqlCompetitors:
    """Competitor repository: the tenant scope is explicit on every query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, competitor: Competitor) -> None:
        await self._session.execute(
            insert(tables.competitors).values(
                id=competitor.id,
                organization_id=competitor.organization_id,
                project_id=competitor.project_id,
                name=competitor.name,
                website=competitor.website,
                notes=competitor.notes,
                created_by=competitor.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> Competitor | None:
        result = await self._session.execute(
            select(tables.competitors).where(
                tables.competitors.c.organization_id == organization_id,
                tables.competitors.c.project_id == project_id,
                tables.competitors.c.id == competitor_id,
            )
        )
        row = result.first()
        return _row_to_competitor(row) if row else None

    async def update(self, competitor: Competitor) -> None:
        await self._session.execute(
            update(tables.competitors)
            .where(
                tables.competitors.c.organization_id == competitor.organization_id,
                tables.competitors.c.project_id == competitor.project_id,
                tables.competitors.c.id == competitor.id,
            )
            .values(
                name=competitor.name,
                website=competitor.website,
                notes=competitor.notes,
                updated_at=datetime.now(UTC),
            )
        )

    async def delete(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> None:
        await self._session.execute(
            delete(tables.competitors).where(
                tables.competitors.c.organization_id == organization_id,
                tables.competitors.c.project_id == project_id,
                tables.competitors.c.id == competitor_id,
            )
        )

    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Competitor]:
        result = await self._session.execute(
            select(tables.competitors)
            .where(
                tables.competitors.c.organization_id == organization_id,
                tables.competitors.c.project_id == project_id,
            )
            .order_by(tables.competitors.c.name)
        )
        return [_row_to_competitor(row) for row in result.all()]


def _row_to_location(row: Row) -> Location:
    return Location(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        competitor_id=row.competitor_id,
        name=row.name,
        address=row.address,
        created_by=row.created_by,
    )


class SqlLocations:
    """Location repository: scoped through the owning competitor."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, location: Location) -> None:
        await self._session.execute(
            insert(tables.locations).values(
                id=location.id,
                organization_id=location.organization_id,
                project_id=location.project_id,
                competitor_id=location.competitor_id,
                name=location.name,
                address=location.address,
                created_by=location.created_by,
            )
        )

    async def get(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
    ) -> Location | None:
        result = await self._session.execute(
            select(tables.locations).where(
                tables.locations.c.organization_id == organization_id,
                tables.locations.c.project_id == project_id,
                tables.locations.c.competitor_id == competitor_id,
                tables.locations.c.id == location_id,
            )
        )
        row = result.first()
        return _row_to_location(row) if row else None

    async def update(self, location: Location) -> None:
        await self._session.execute(
            update(tables.locations)
            .where(
                tables.locations.c.organization_id == location.organization_id,
                tables.locations.c.project_id == location.project_id,
                tables.locations.c.competitor_id == location.competitor_id,
                tables.locations.c.id == location.id,
            )
            .values(
                name=location.name,
                address=location.address,
                updated_at=datetime.now(UTC),
            )
        )

    async def delete(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(tables.locations).where(
                tables.locations.c.organization_id == organization_id,
                tables.locations.c.project_id == project_id,
                tables.locations.c.competitor_id == competitor_id,
                tables.locations.c.id == location_id,
            )
        )

    async def list_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> list[Location]:
        result = await self._session.execute(
            select(tables.locations)
            .where(
                tables.locations.c.organization_id == organization_id,
                tables.locations.c.project_id == project_id,
                tables.locations.c.competitor_id == competitor_id,
            )
            .order_by(tables.locations.c.name)
        )
        return [_row_to_location(row) for row in result.all()]


# --- Services + Observations (ticket #34) -----------------------------------


def _row_to_service(row: Row) -> Service:
    return Service(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        name=row.name,
        created_by=row.created_by,
    )


class SqlServices:
    """Service catalog: tenant-scoped; names dedupe case-insensitively per
    project (enforced by the unique index + a pre-insert check that maps
    to a typed 409)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, service: Service) -> None:
        await self._session.execute(
            insert(tables.services).values(
                id=service.id,
                organization_id=service.organization_id,
                project_id=service.project_id,
                name=service.name,
                created_by=service.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, service_id: UUID
    ) -> Service | None:
        result = await self._session.execute(
            select(tables.services).where(
                tables.services.c.organization_id == organization_id,
                tables.services.c.project_id == project_id,
                tables.services.c.id == service_id,
            )
        )
        row = result.first()
        return _row_to_service(row) if row else None

    async def get_by_name(
        self, organization_id: UUID, project_id: UUID, name: str
    ) -> Service | None:
        result = await self._session.execute(
            select(tables.services).where(
                tables.services.c.organization_id == organization_id,
                tables.services.c.project_id == project_id,
                func.lower(tables.services.c.name) == name.lower(),
            )
        )
        row = result.first()
        return _row_to_service(row) if row else None

    async def delete(
        self, organization_id: UUID, project_id: UUID, service_id: UUID
    ) -> None:
        await self._session.execute(
            delete(tables.services).where(
                tables.services.c.organization_id == organization_id,
                tables.services.c.project_id == project_id,
                tables.services.c.id == service_id,
            )
        )

    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Service]:
        result = await self._session.execute(
            select(tables.services)
            .where(
                tables.services.c.organization_id == organization_id,
                tables.services.c.project_id == project_id,
            )
            .order_by(tables.services.c.name)
        )
        return [_row_to_service(row) for row in result.all()]


def _row_to_observation(row: Row) -> Observation:
    return Observation(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        competitor_id=row.competitor_id,
        service_id=row.service_id,
        location_id=row.location_id,
        kind=row.kind,
        price_amount=row.price_amount,
        price_currency=row.price_currency,
        observed_on=row.observed_on,
        confidence=row.confidence,
        extraction_version=row.extraction_version,
        approval_state=row.approval_state,
        superseded_by=row.superseded_by,
        created_by=row.created_by,
    )


class SqlObservations:
    """Observation repository: stored, never overwritten — the only
    in-place write is the approval-state flip."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, observation: Observation) -> None:
        await self._session.execute(
            insert(tables.observations).values(
                id=observation.id,
                organization_id=observation.organization_id,
                project_id=observation.project_id,
                competitor_id=observation.competitor_id,
                service_id=observation.service_id,
                location_id=observation.location_id,
                kind=observation.kind,
                price_amount=observation.price_amount,
                price_currency=observation.price_currency,
                observed_on=observation.observed_on,
                confidence=observation.confidence,
                extraction_version=observation.extraction_version,
                approval_state=observation.approval_state,
                superseded_by=observation.superseded_by,
                created_by=observation.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, observation_id: UUID
    ) -> Observation | None:
        result = await self._session.execute(
            select(tables.observations).where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.id == observation_id,
            )
        )
        row = result.first()
        return _row_to_observation(row) if row else None

    async def update_state(
        self,
        organization_id: UUID,
        project_id: UUID,
        observation_id: UUID,
        *,
        approval_state: str,
        superseded_by: UUID | None,
    ) -> None:
        await self._session.execute(
            update(tables.observations)
            .where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.id == observation_id,
            )
            .values(
                approval_state=approval_state,
                superseded_by=superseded_by,
                updated_at=datetime.now(UTC),
            )
        )

    async def list_current_approved_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
    ) -> list[Observation]:
        result = await self._session.execute(
            select(tables.observations)
            .where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.competitor_id == competitor_id,
                tables.observations.c.approval_state == "approved",
                tables.observations.c.superseded_by.is_(None),
            )
            .order_by(tables.observations.c.created_at.desc())
        )
        return [_row_to_observation(row) for row in result.all()]

    async def list_pending_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Observation]:
        result = await self._session.execute(
            select(tables.observations)
            .where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.approval_state == "pending",
            )
            .order_by(tables.observations.c.created_at)
        )
        return [_row_to_observation(row) for row in result.all()]

    async def list_approved_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        kind: str,
    ) -> list[Observation]:
        result = await self._session.execute(
            select(tables.observations)
            .where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.competitor_id == competitor_id,
                tables.observations.c.kind == kind,
                tables.observations.c.approval_state == "approved",
            )
            .order_by(tables.observations.c.observed_on)
        )
        return [_row_to_observation(row) for row in result.all()]

    async def count_referencing_service(
        self, organization_id: UUID, project_id: UUID, service_id: UUID
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(tables.observations)
            .where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.service_id == service_id,
            )
        )
        return int(result.scalar_one())

    async def list_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> list[Observation]:
        result = await self._session.execute(
            select(tables.observations)
            .where(
                tables.observations.c.organization_id == organization_id,
                tables.observations.c.project_id == project_id,
                tables.observations.c.competitor_id == competitor_id,
            )
            .order_by(tables.observations.c.created_at)
        )
        return [_row_to_observation(row) for row in result.all()]


def _row_to_evidence(row: Row) -> EvidenceLink:
    return EvidenceLink(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        competitor_id=row.competitor_id,
        observation_id=row.observation_id,
        target_kind=row.target_kind,
        target_id=row.target_id,
        excerpt=row.excerpt,
        excerpt_start=row.excerpt_start,
        excerpt_end=row.excerpt_end,
        approval_state=row.approval_state,
        created_by=row.created_by,
    )


class SqlEvidence:
    """Evidence repository: links a competitor to an opaque research
    target. Scope flows through the competitor row; no cross-module
    reads (plan §14.4 rule 2)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, link: EvidenceLink) -> None:
        await self._session.execute(
            insert(tables.evidence_links).values(
                id=link.id,
                organization_id=link.organization_id,
                project_id=link.project_id,
                competitor_id=link.competitor_id,
                observation_id=link.observation_id,
                target_kind=link.target_kind,
                target_id=link.target_id,
                excerpt=link.excerpt,
                excerpt_start=link.excerpt_start,
                excerpt_end=link.excerpt_end,
                approval_state=link.approval_state,
                created_by=link.created_by,
            )
        )

    async def get(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        evidence_id: UUID,
    ) -> EvidenceLink | None:
        result = await self._session.execute(
            select(tables.evidence_links).where(
                tables.evidence_links.c.organization_id == organization_id,
                tables.evidence_links.c.project_id == project_id,
                tables.evidence_links.c.competitor_id == competitor_id,
                tables.evidence_links.c.id == evidence_id,
            )
        )
        row = result.first()
        return _row_to_evidence(row) if row else None

    async def delete(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        evidence_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(tables.evidence_links).where(
                tables.evidence_links.c.organization_id == organization_id,
                tables.evidence_links.c.project_id == project_id,
                tables.evidence_links.c.competitor_id == competitor_id,
                tables.evidence_links.c.id == evidence_id,
            )
        )

    async def list_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        *,
        target_kind: str | None = None,
        observation_id: UUID | None = None,
    ) -> list[EvidenceLink]:
        conditions = [
            tables.evidence_links.c.organization_id == organization_id,
            tables.evidence_links.c.project_id == project_id,
            tables.evidence_links.c.competitor_id == competitor_id,
        ]
        if target_kind is not None:
            conditions.append(tables.evidence_links.c.target_kind == target_kind)
        if observation_id is not None:
            conditions.append(
                tables.evidence_links.c.observation_id == observation_id
            )
        result = await self._session.execute(
            select(tables.evidence_links)
            .where(*conditions)
            .order_by(tables.evidence_links.c.created_at)
        )
        return [_row_to_evidence(row) for row in result.all()]
