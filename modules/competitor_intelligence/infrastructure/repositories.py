"""SQLAlchemy implementations of the competitor repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (mirrors the platform and
research contracts, plan §8.2).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.competitor_intelligence.domain.entities import Competitor, Location
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
