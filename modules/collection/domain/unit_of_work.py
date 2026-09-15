"""The collection unit of work: the platform's repositories plus this
module's own, in one transaction (mirrors CompetitorUnit/ResearchUnit).

Collection requires Platform only (plan §14.3): competitor references
stay opaque UUIDs and cross-module existence validation is deferred to
Phase 5 — so this unit extends PlatformUnit, never a competitor type.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from modules.collection.domain.entities import Job, JobRun, Snapshot
from modules.platform.domain.unit_of_work import PlatformUnit


class Snapshots(Protocol):
    """Snapshot repository — the tenant scope is explicit on every query,
    mirroring the research/competitor contracts."""

    async def create(self, snapshot: Snapshot) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, snapshot_id: UUID
    ) -> Snapshot | None: ...
    async def latest_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        connector_kind: str,
    ) -> Snapshot | None: ...
    async def list_for_competitor(
        self,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        connector_kind: str,
    ) -> list[Snapshot]: ...


class Jobs(Protocol):
    """Schedule repository. The scheduler's claim is transactional:
    creating the run row, the outbox event, and advancing next_due_at
    commit together (ADR-004), so a claimed job can never be claimed
    twice."""

    async def create(self, job: Job) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, job_id: UUID
    ) -> Job | None: ...
    async def list_for_competitor(
        self, organization_id: UUID, project_id: UUID, competitor_id: UUID
    ) -> list[Job]: ...
    async def delete(
        self, organization_id: UUID, project_id: UUID, job_id: UUID
    ) -> None: ...
    async def list_due(self, now: datetime, *, limit: int = 100) -> list[Job]: ...
    async def advance(
        self,
        organization_id: UUID,
        project_id: UUID,
        job_id: UUID,
        *,
        next_due_at: datetime,
        failures: int,
    ) -> None: ...


class JobRuns(Protocol):
    """Attempt repository — one row per collection attempt."""

    async def create(self, run: JobRun) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, run_id: UUID
    ) -> JobRun | None: ...
    async def list_pending(self, *, limit: int = 100) -> list[JobRun]: ...
    async def mark_result(
        self,
        organization_id: UUID,
        project_id: UUID,
        run_id: UUID,
        *,
        status: str,
        snapshot_id: UUID | None,
        error: str | None,
    ) -> None: ...
    async def count_since(
        self, organization_id: UUID, project_id: UUID, since: datetime
    ) -> int: ...
    async def list_for_job(
        self, organization_id: UUID, project_id: UUID, job_id: UUID
    ) -> list[JobRun]: ...


__all__ = ["Snapshots", "Jobs", "JobRuns", "CollectionUnit"]


class CollectionUnit(PlatformUnit, Protocol):
    """One transaction worth of repositories: the platform's plus
    collection's own."""

    snapshots: Snapshots
    jobs: Jobs
    job_runs: JobRuns
