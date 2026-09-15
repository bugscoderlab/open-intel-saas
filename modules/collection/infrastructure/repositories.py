"""SQLAlchemy implementations of the collection repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (mirrors the platform, research
and competitor contracts, plan §8.2).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.collection.domain.entities import Job, JobRun, Snapshot
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
        interval_seconds=row.interval_seconds,
        next_due_at=row.next_due_at,
        enabled=row.enabled,
        failures=row.failures,
        created_by=row.requested_by,
    )


def _row_to_run(row: Row) -> JobRun:
    return JobRun(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        job_id=row.job_id,
        competitor_id=row.competitor_id,
        connector_kind=row.connector_kind,
        url=row.url,
        status=row.status,
        snapshot_id=row.snapshot_id,
        error=row.error,
        attempt=row.attempt,
        requested_by=row.requested_by,
        run_at=row.run_at,
        finished_at=row.finished_at,
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
    """Schedule repository. ``list_due`` is the scheduler's claim source;
    the claim itself (run row + outbox event + advance) commits in one
    transaction in the service layer, so a due job is never claimed
    twice."""

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
                interval_seconds=job.interval_seconds,
                next_due_at=job.next_due_at,
                enabled=job.enabled,
                failures=job.failures,
                # #42 leftover columns, unused since job_runs took over
                # attempts — satisfy the NOT NULL with a neutral value.
                status="pending",
                requested_by=job.created_by,
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

    async def list_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> list[Job]:
        result = await self._session.execute(
            select(tables.jobs)
            .where(
                tables.jobs.c.organization_id == organization_id,
                tables.jobs.c.project_id == project_id,
                tables.jobs.c.competitor_id == competitor_id,
            )
            .order_by(tables.jobs.c.created_at)
        )
        return [_row_to_job(row) for row in result.all()]

    async def delete(
        self, organization_id: UUID, project_id: UUID, job_id: UUID
    ) -> None:
        await self._session.execute(
            delete(tables.jobs).where(
                tables.jobs.c.organization_id == organization_id,
                tables.jobs.c.project_id == project_id,
                tables.jobs.c.id == job_id,
            )
        )

    async def list_due(self, now: datetime, *, limit: int = 100) -> list[Job]:
        result = await self._session.execute(
            select(tables.jobs)
            .where(
                tables.jobs.c.enabled.is_(True),
                tables.jobs.c.next_due_at.is_not(None),
                tables.jobs.c.next_due_at <= now,
            )
            .order_by(tables.jobs.c.next_due_at)
            .limit(limit)
        )
        return [_row_to_job(row) for row in result.all()]

    async def advance(
        self,
        organization_id: UUID,
        project_id: UUID,
        job_id: UUID,
        *,
        next_due_at: datetime,
        failures: int,
    ) -> None:
        await self._session.execute(
            update(tables.jobs)
            .where(
                tables.jobs.c.organization_id == organization_id,
                tables.jobs.c.project_id == project_id,
                tables.jobs.c.id == job_id,
            )
            .values(
                next_due_at=next_due_at,
                failures=failures,
                updated_at=func.now(),
            )
        )


class SqlJobRuns:
    """Attempt repository — one row per collection attempt."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: JobRun) -> None:
        await self._session.execute(
            insert(tables.job_runs).values(
                id=run.id,
                organization_id=run.organization_id,
                project_id=run.project_id,
                job_id=run.job_id,
                competitor_id=run.competitor_id,
                connector_kind=run.connector_kind,
                url=run.url,
                status=run.status,
                snapshot_id=run.snapshot_id,
                error=run.error,
                attempt=run.attempt,
                requested_by=run.requested_by,
                run_at=run.run_at,
                finished_at=run.finished_at,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, run_id: UUID
    ) -> JobRun | None:
        result = await self._session.execute(
            select(tables.job_runs).where(
                tables.job_runs.c.organization_id == organization_id,
                tables.job_runs.c.project_id == project_id,
                tables.job_runs.c.id == run_id,
            )
        )
        row = result.first()
        return _row_to_run(row) if row else None

    async def list_pending(self, *, limit: int = 100) -> list[JobRun]:
        result = await self._session.execute(
            select(tables.job_runs)
            .where(tables.job_runs.c.status == "pending")
            .order_by(tables.job_runs.c.run_at)
            .limit(limit)
        )
        return [_row_to_run(row) for row in result.all()]

    async def mark_result(
        self,
        organization_id: UUID,
        project_id: UUID,
        run_id: UUID,
        *,
        status: str,
        snapshot_id: UUID | None,
        error: str | None,
    ) -> None:
        await self._session.execute(
            update(tables.job_runs)
            .where(
                tables.job_runs.c.organization_id == organization_id,
                tables.job_runs.c.project_id == project_id,
                tables.job_runs.c.id == run_id,
            )
            .values(
                status=status,
                snapshot_id=snapshot_id,
                error=error,
                finished_at=func.now(),
            )
        )

    async def count_since(
        self, organization_id: UUID, project_id: UUID, since: datetime
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(tables.job_runs)
            .where(
                tables.job_runs.c.organization_id == organization_id,
                tables.job_runs.c.project_id == project_id,
                tables.job_runs.c.run_at >= since,
            )
        )
        return int(result.scalar_one())

    async def list_for_job(
        self, organization_id: UUID, project_id: UUID, job_id: UUID
    ) -> list[JobRun]:
        result = await self._session.execute(
            select(tables.job_runs)
            .where(
                tables.job_runs.c.organization_id == organization_id,
                tables.job_runs.c.project_id == project_id,
                tables.job_runs.c.job_id == job_id,
            )
            .order_by(tables.job_runs.c.run_at.desc())
        )
        return [_row_to_run(row) for row in result.all()]
