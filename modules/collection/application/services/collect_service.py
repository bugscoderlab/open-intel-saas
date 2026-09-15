"""Collection use cases (ticket #42, spec #41) — the Collection job slice.

On-demand website collection follows the research ADR-004 pattern: the
request creates the job row + a CollectionJobRequested outbox event in
one transaction (PDR-003) and returns 202; the drain runs off-request.
The drain is failure-isolated per job: a failed fetch marks that job
failed (typed error + audit row) and never blocks the remaining jobs,
and previously stored snapshots are never touched by failures.
"""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse
from uuid import UUID, uuid4

from modules.collection.domain.entities import (
    CONNECTOR_KINDS,
    JOB_FAILED,
    JOB_PENDING,
    JOB_SNAPSHOT_CREATED,
    JOB_UNCHANGED,
    Job,
    Snapshot,
)
from modules.collection.domain.errors import FetchQuotaExceededError
from modules.collection.domain.events import (
    COLLECTION_JOB_REQUESTED,
    COLLECTION_SNAPSHOT_CREATED,
)
from modules.collection.domain.ports import WebsiteFetcher
from modules.collection.domain.unit_of_work import CollectionUnit
from modules.platform.application.errors import NotFoundError, ValidationError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry, OutboxEvent
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission

# A fetch counts against the quota for 24 hours from the request.
QUOTA_WINDOW_HOURS = 24


async def _load_project(unit: CollectionUnit, project_id: UUID):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    return project


async def request_collection(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    connector_kind: str,
    url: str,
    quota: int | None,
) -> Job:
    """collection.run — enqueue one on-demand collection; the drain
    performs the fetch off-request. The competitor reference is opaque
    (existence validation is Phase 5, spec #41); the project scope is
    real and authorized here."""
    project = await _load_project(unit, project_id)
    await authz.require(
        principal,
        Permission.COLLECTION_RUN,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if connector_kind not in CONNECTOR_KINDS:
        raise ValidationError(f"connector_kind must be one of {CONNECTOR_KINDS}")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("url must be an absolute http(s) URL")
    if quota is not None:
        since = datetime.now(UTC) - timedelta(hours=QUOTA_WINDOW_HOURS)
        attempted = await unit.jobs.count_since(
            project.organization_id, project_id, since
        )
        if attempted >= quota:
            raise FetchQuotaExceededError(
                f"fetch quota of {quota} per project per "
                f"{QUOTA_WINDOW_HOURS}h is exhausted"
            )
    job = Job(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        competitor_id=competitor_id,
        connector_kind=connector_kind,
        url=url,
        status=JOB_PENDING,
        snapshot_id=None,
        error=None,
        requested_by=principal.app_user_id,
    )
    await unit.jobs.create(job)
    await unit.outbox.add(
        OutboxEvent(
            event_type=COLLECTION_JOB_REQUESTED,
            payload={
                "job_id": str(job.id),
                "organization_id": str(project.organization_id),
                "project_id": str(project_id),
            },
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="collection.run",
            target_type="collection_job",
            target_id=str(job.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "connector_kind": connector_kind,
                "url": url,
            },
        )
    )
    return job


def normalize_content(content: str) -> str:
    """Canonical form for hashing: surrounding whitespace only — the raw
    payload keeps whatever the server sent (snapshots are raw captures)."""
    return content.strip()


async def _run_job(unit: CollectionUnit, fetcher: WebsiteFetcher, job: Job) -> None:
    """One job, failure-isolated: any fetch error marks THIS job failed
    with the error and an audit row, and the drain moves on. The catch
    is deliberately broad — a poison job (buggy adapter included) must
    never stall the batch or roll back other jobs' work."""
    try:
        page = await fetcher.fetch(job.url)
    except Exception as exc:
        await unit.jobs.mark_result(
            job.organization_id,
            job.project_id,
            job.id,
            status=JOB_FAILED,
            snapshot_id=None,
            error=str(exc),
        )
        await unit.audit.record(
            AuditEntry(
                actor_id=job.requested_by,
                action="collection.failed",
                target_type="collection_job",
                target_id=str(job.id),
                organization_id=job.organization_id,
                payload={"project_id": str(job.project_id), "error": str(exc)},
            )
        )
        return
    digest = sha256(normalize_content(page.content).encode("utf-8")).hexdigest()
    latest = await unit.snapshots.latest_for_competitor(
        job.organization_id, job.project_id, job.competitor_id, job.connector_kind
    )
    if latest is not None and latest.content_hash == digest:
        await unit.jobs.mark_result(
            job.organization_id,
            job.project_id,
            job.id,
            status=JOB_UNCHANGED,
            snapshot_id=latest.id,
            error=None,
        )
        await unit.audit.record(
            AuditEntry(
                actor_id=job.requested_by,
                action="collection.unchanged",
                target_type="collection_job",
                target_id=str(job.id),
                organization_id=job.organization_id,
                payload={"project_id": str(job.project_id)},
            )
        )
        return
    snapshot = Snapshot(
        id=uuid4(),
        organization_id=job.organization_id,
        project_id=job.project_id,
        competitor_id=job.competitor_id,
        connector_kind=job.connector_kind,
        url=job.url,
        content_hash=digest,
        raw_payload=page.content,
        captured_at=page.fetched_at,
        created_by=job.requested_by,
    )
    await unit.snapshots.create(snapshot)
    await unit.jobs.mark_result(
        job.organization_id,
        job.project_id,
        job.id,
        status=JOB_SNAPSHOT_CREATED,
        snapshot_id=snapshot.id,
        error=None,
    )
    await unit.outbox.add(
        OutboxEvent(
            event_type=COLLECTION_SNAPSHOT_CREATED,
            payload={
                "snapshot_id": str(snapshot.id),
                "organization_id": str(job.organization_id),
                "project_id": str(job.project_id),
            },
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=job.requested_by,
            action="collection.snapshot_created",
            target_type="collection_snapshot",
            target_id=str(snapshot.id),
            organization_id=job.organization_id,
            payload={"project_id": str(job.project_id)},
        )
    )


async def drain_pending_jobs(unit_factory, fetcher: WebsiteFetcher, *, limit: int = 100) -> int:
    """Drain pending jobs in ONE transaction, off-request (ADR-004).

    Each job is failure-isolated inside the drain (see _run_job), so one
    bad fetch can never stall or roll back the batch. Tests call this
    directly for determinism; the production poll loop lives in
    infrastructure/dispatcher.py."""
    unit = unit_factory()
    async with unit:
        jobs = await unit.jobs.list_pending(limit=limit)
        for job in jobs:
            await _run_job(unit, fetcher, job)
        await unit.commit()
        return len(jobs)


async def list_snapshots(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    connector_kind: str,
) -> list[Snapshot]:
    """snapshot.read — newest first; the connector filter keeps website
    captures separate from later connector kinds on the same competitor."""
    project = await _load_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SNAPSHOT_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if connector_kind not in CONNECTOR_KINDS:
        raise ValidationError(f"connector_kind must be one of {CONNECTOR_KINDS}")
    return await unit.snapshots.list_for_competitor(
        project.organization_id, project_id, competitor_id, connector_kind
    )


async def get_snapshot(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    snapshot_id: UUID,
) -> Snapshot:
    """snapshot.read — single capture with the raw payload."""
    project = await _load_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SNAPSHOT_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    snapshot = await unit.snapshots.get(
        project.organization_id, project_id, snapshot_id
    )
    if snapshot is None:
        raise NotFoundError("snapshot not found")
    return snapshot
