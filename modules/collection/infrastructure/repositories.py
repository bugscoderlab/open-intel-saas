"""SQLAlchemy implementations of the collection repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (mirrors the platform, research
and competitor contracts, plan §8.2).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.collection.domain.entities import Job, Snapshot
from modules.collection.infrastructure import db as tables


def _row_to_snapshot(row: Row) -> Snapshot:
    return Snapshot(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        competitor_id=row.competitor_id,
        connector_kind=row.connector_kind,
        url=row.url,
        content_hash=row.content_hash,
        raw_payload=row.raw_payload,
        captured_at=row.captured_at,
        created_by=row.created_by,
    )


def _row_to_job(row: Row) -> Job:
    return Job(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        competitor_id=row.competitor_id,
        connector_kind=row.connector_kind,
        url=row.url,
        status=row.status,
        snapshot_id=row.snapshot_id,
        error=row.error,
        requested_by=row.requested_by,
    )


class SqlSnapshots:
    """Snapshot repository: the tenant scope is explicit on every query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, snapshot: Snapshot) -> None:
        await self._session.execute(
            insert(tables.snapshots).values(
                id=snapshot.id,
                organization_id=snapshot.organization_id,
                project_id=snapshot.project_id,
                competitor_id=snapshot.competitor_id,
                connector_kind=snapshot.connector_kind,
                url=snapshot.url,
                content_hash=snapshot.content_hash,
                raw_payload=snapshot.raw_payload,
                captured_at=snapshot.captured_at,
                created_by=snapshot.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, snapshot_id: UUID
    ) -> Snapshot | None:
        result = await self._session.execute(
            select(tables.snapshots).where(
                tables.snapshots.c.organization_id == organization_id,
                tables.snapshots.c.project_id == project_id,
                tables.snapshots.c.id == snapshot_id,
            )
        )
        row = result.first()
        return _row_to_snapshot(row) if row else None

    async def latest_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        connector_kind: str,
    ) -> Snapshot | None:
        result = await self._session.execute(
            select(tables.snapshots)
            .where(
                tables.snapshots.c.organization_id == organization_id,
                tables.snapshots.c.project_id == project_id,
                tables.snapshots.c.competitor_id == competitor_id,
                tables.snapshots.c.connector_kind == connector_kind,
            )
            .order_by(tables.snapshots.c.captured_at.desc())
            .limit(1)
        )
        row = result.first()
        return _row_to_snapshot(row) if row else None

    async def list_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        connector_kind: str,
    ) -> list[Snapshot]:
        result = await self._session.execute(
            select(tables.snapshots)
            .where(
                tables.snapshots.c.organization_id == organization_id,
                tables.snapshots.c.project_id == project_id,
                tables.snapshots.c.competitor_id == competitor_id,
                tables.snapshots.c.connector_kind == connector_kind,
            )
            .order_by(tables.snapshots.c.captured_at.desc())
        )
        return [_row_to_snapshot(row) for row in result.all()]


class SqlJobs:
    """Job repository: one row per collection attempt."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job: Job) -> None:
        await self._session.execute(
            insert(tables.jobs).values(
                id=job.id,
                organization_id=job.organization_id,
                project_id=job.project_id,
                competitor_id=job.competitor_id,
                connector_kind=job.connector_kind,
                url=job.url,
                status=job.status,
                snapshot_id=job.snapshot_id,
                error=job.error,
                requested_by=job.requested_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, job_id: UUID
    ) -> Job | None:
        result = await self._session.execute(
            select(tables.jobs).where(
                tables.jobs.c.organization_id == organization_id,
                tables.jobs.c.project_id == project_id,
                tables.jobs.c.id == job_id,
            )
        )
        row = result.first()
        return _row_to_job(row) if row else None

    async def list_pending(self, *, limit: int = 100) -> list[Job]:
        result = await self._session.execute(
            select(tables.jobs)
            .where(tables.jobs.c.status == "pending")
            .order_by(tables.jobs.c.created_at)
            .limit(limit)
        )
        return [_row_to_job(row) for row in result.all()]

    async def mark_result(
        self,
        organization_id: UUID,
        project_id: UUID,
        job_id: UUID,
        *,
        status: str,
        snapshot_id: UUID | None,
        error: str | None,
    ) -> None:
        await self._session.execute(
            update(tables.jobs)
            .where(
                tables.jobs.c.organization_id == organization_id,
                tables.jobs.c.project_id == project_id,
                tables.jobs.c.id == job_id,
            )
            .values(
                status=status,
                snapshot_id=snapshot_id,
                error=error,
                updated_at=func.now(),
            )
        )

    async def count_since(
        self, organization_id: UUID, project_id: UUID, since: datetime
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(tables.jobs)
            .where(
                tables.jobs.c.organization_id == organization_id,
                tables.jobs.c.project_id == project_id,
                tables.jobs.c.created_at >= since,
            )
        )
        return int(result.scalar_one())
