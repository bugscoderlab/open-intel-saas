"""Schedule use cases (ticket #44, spec #41) — the scheduled-jobs slice.

A Job is a schedule (competitor + connector + interval). Editors manage
them over the API; the scheduler claims due schedules by creating a
job_run + a CollectionDue outbox event + advancing next_due_at in ONE
transaction (ADR-004), so a due job is never claimed twice and the
worker loop is the same drain the on-demand flow uses. Runs then record
success/unchanged/failure with retry/backoff state on the schedule.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from modules.collection.application.services import collect_service
from modules.collection.domain.entities import CONNECTOR_KINDS, Job
from modules.collection.domain.events import COLLECTION_DUE
from modules.collection.domain.unit_of_work import CollectionUnit
from modules.platform.application.errors import NotFoundError, ValidationError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def _authorized_project(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    project_id: UUID,
    permission: str,
):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        permission,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return project


async def create_job(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    connector_kind: str,
    url: str,
    interval_seconds: int,
    quota: int | None,
) -> Job:
    """collection.job.manage — create a schedule; the first run is due
    one interval from now."""
    project = await _authorized_project(
        unit, authz, principal, project_id, Permission.COLLECTION_JOB_MANAGE
    )
    if connector_kind not in CONNECTOR_KINDS:
        raise ValidationError(f"connector_kind must be one of {CONNECTOR_KINDS}")
    collect_service._validate_url(url)
    if interval_seconds < 1:
        raise ValidationError("interval_seconds must be at least 1")
    await collect_service._check_quota(
        unit, project.organization_id, project_id, quota
    )
    job = Job(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        competitor_id=competitor_id,
        connector_kind=connector_kind,
        url=url,
        interval_seconds=interval_seconds,
        next_due_at=datetime.now(UTC) + timedelta(seconds=interval_seconds),
        enabled=True,
        failures=0,
        created_by=principal.app_user_id,
    )
    await unit.jobs.create(job)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="collection.job.create",
            target_type="collection_job",
            target_id=str(job.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "connector_kind": connector_kind,
                "url": url,
                "interval_seconds": interval_seconds,
            },
        )
    )
    return job


async def list_jobs(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
) -> list[Job]:
    """collection.job.manage — list a competitor's schedules (editor+)."""
    project = await _authorized_project(
        unit, authz, principal, project_id, Permission.COLLECTION_JOB_MANAGE
    )
    return await unit.jobs.list_for_competitor(
        project.organization_id, project_id, competitor_id
    )


async def delete_job(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    job_id: UUID,
) -> None:
    """collection.job.manage — stop future scheduled runs. Deleting the
    schedule never touches the snapshots or runs it already produced."""
    project = await _authorized_project(
        unit, authz, principal, project_id, Permission.COLLECTION_JOB_MANAGE
    )
    job = await unit.jobs.get(project.organization_id, project_id, job_id)
    if job is None or job.competitor_id != competitor_id:
        raise NotFoundError("collection job not found")
    await unit.jobs.delete(project.organization_id, project_id, job_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="collection.job.delete",
            target_type="collection_job",
            target_id=str(job_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )


async def run_job_now(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    job_id: UUID,
    quota: int | None,
):
    """collection.run — force an immediate ad-hoc run of a schedule.
    The run is scheduled through the same pipeline as due claims."""
    project = await _authorized_project(
        unit, authz, principal, project_id, Permission.COLLECTION_RUN
    )
    job = await unit.jobs.get(project.organization_id, project_id, job_id)
    if job is None or job.competitor_id != competitor_id:
        raise NotFoundError("collection job not found")
    await collect_service._check_quota(
        unit, project.organization_id, project_id, quota
    )
    return await collect_service._record_run(
        unit,
        project_id=project_id,
        competitor_id=competitor_id,
        connector_kind=job.connector_kind,
        url=job.url,
        job_id=job.id,
        attempt=job.failures,
        requested_by=principal.app_user_id,
        event_type=COLLECTION_DUE,
    )


async def list_runs(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    job_id: UUID,
):
    """snapshot.read — a schedule's run history, newest first."""
    project = await _authorized_project(
        unit, authz, principal, project_id, Permission.SNAPSHOT_READ
    )
    job = await unit.jobs.get(project.organization_id, project_id, job_id)
    if job is None:
        raise NotFoundError("collection job not found")
    return await unit.job_runs.list_for_job(
        project.organization_id, project_id, job_id
    )


async def claim_due_jobs(unit: CollectionUnit, now: datetime, *, limit: int = 100) -> int:
    """Claim due schedules: per job, in the caller's transaction, create
    the run row + CollectionDue outbox event and advance next_due_at by
    one plain interval. Claimed = never double-claimed (ADR-004); run
    outcomes re-advance the schedule through the drain (success) or into
    backoff (failure)."""
    due = await unit.jobs.list_due(now, limit=limit)
    for job in due:
        await collect_service._record_run(
            unit,
            project_id=job.project_id,
            competitor_id=job.competitor_id,
            connector_kind=job.connector_kind,
            url=job.url,
            job_id=job.id,
            attempt=job.failures,
            requested_by=job.created_by,
            event_type=COLLECTION_DUE,
        )
        await unit.jobs.advance(
            job.organization_id,
            job.project_id,
            job.id,
            next_due_at=now + timedelta(seconds=job.interval_seconds),
            failures=job.failures,
        )
    return len(due)
