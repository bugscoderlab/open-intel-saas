"""SQLAlchemy repositories for extraction (ticket #50)."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.extraction.domain.entities import ExtractionRun
from modules.extraction.domain.unit_of_work import ExtractionRuns
from modules.extraction.infrastructure.db import extraction_runs


def _row_to_run(row: Any) -> ExtractionRun:
    return ExtractionRun(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        competitor_id=row.competitor_id,
        snapshot_id=row.snapshot_id,
        status=row.status,
        extraction_version=row.extraction_version,
        error=row.error,
        requested_by=row.requested_by,
    )


class SqlExtractionRuns(ExtractionRuns):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: ExtractionRun) -> None:
        await self._session.execute(
            extraction_runs.insert().values(
                id=run.id,
                organization_id=run.organization_id,
                project_id=run.project_id,
                competitor_id=run.competitor_id,
                snapshot_id=run.snapshot_id,
                status=run.status,
                extraction_version=run.extraction_version,
                error=run.error,
                requested_by=run.requested_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, run_id: UUID
    ) -> ExtractionRun | None:
        result = await self._session.execute(
            select(extraction_runs).where(
                extraction_runs.c.organization_id == organization_id,
                extraction_runs.c.project_id == project_id,
                extraction_runs.c.id == run_id,
            )
        )
        row = result.first()
        return _row_to_run(row) if row is not None else None

    async def list_pending(self, *, limit: int = 100) -> list[ExtractionRun]:
        result = await self._session.execute(
            select(extraction_runs)
            .where(extraction_runs.c.status == "pending")
            .order_by(extraction_runs.c.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [_row_to_run(row) for row in result.all()]

    async def mark_result(
        self,
        organization_id: UUID,
        project_id: UUID,
        run_id: UUID,
        *,
        status: str,
        error: str | None,
    ) -> None:
        await self._session.execute(
            update(extraction_runs)
            .where(
                extraction_runs.c.organization_id == organization_id,
                extraction_runs.c.project_id == project_id,
                extraction_runs.c.id == run_id,
            )
            .values(status=status, error=error, finished_at=func.now())
        )

    async def find_for_snapshot(
        self,
        organization_id: UUID,
        project_id: UUID,
        snapshot_id: UUID,
        extraction_version: str,
    ) -> ExtractionRun | None:
        result = await self._session.execute(
            select(extraction_runs)
            .where(
                extraction_runs.c.organization_id == organization_id,
                extraction_runs.c.project_id == project_id,
                extraction_runs.c.snapshot_id == snapshot_id,
                extraction_runs.c.extraction_version == extraction_version,
            )
            .order_by(extraction_runs.c.created_at.desc())
            .limit(1)
        )
        row = result.first()
        return _row_to_run(row) if row is not None else None
