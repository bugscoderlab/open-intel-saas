"""Collection use cases (tickets #42/#44, spec #41) — the Collection job
slice.

On-demand website collection follows the research ADR-004 pattern: the
request creates the job_run row + a CollectionJobRequested outbox event
in one transaction (PDR-003) and returns 202; the drain runs off-request.
The drain is failure-isolated per run: a failed fetch marks that run
failed (typed error + audit row) and never blocks the remaining runs,
and previously stored snapshots are never touched by failures.

Scheduled collection (ticket #44) runs through the SAME pipeline: the
scheduler claims due schedules by creating job_run rows + CollectionDue
outbox events (see job_service), and this drain processes them
identically to ad-hoc runs. On a terminal result the parent schedule is
advanced — plain interval on success, exponential backoff on failure.
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
    JobRun,
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
# Scheduled-run retry backoff: base * 2^(failures-1), capped (ticket #44
# assumption, recorded on the issue).
RETRY_BACKOFF_BASE_SECONDS = 60
RETRY_BACKOFF_CAP_SECONDS = 3600


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("url must be an absolute http(s) URL")


async def _load_project(unit: CollectionUnit, project_id: UUID):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    return project


async def _check_quota(
    unit: CollectionUnit, organization_id: UUID, project_id: UUID, quota: int | None
) -> None:
    if quota is None:
        return
    since = datetime.now(UTC) - timedelta(hours=QUOTA_WINDOW_HOURS)
    attempted = await unit.job_runs.count_since(organization_id, project_id, since)
    if attempted >= quota:
        raise FetchQuotaExceededError(
            f"fetch quota of {quota} per project per "
            f"{QUOTA_WINDOW_HOURS}h is exhausted"
        )


async def _record_run(
    unit: CollectionUnit,
    *,
    project_id: UUID,
    competitor_id: UUID,
    connector_kind: str,
    url: str,
    job_id: UUID | None,
    attempt: int,
    requested_by: UUID,
    event_type: str,
) -> JobRun:
    """Persist one pending attempt + its outbox event in the current
    transaction (the ADR-004 claim/enqueue)."""
    project = await _load_project(unit, project_id)
    run = JobRun(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        job_id=job_id,
        competitor_id=competitor_id,
        connector_kind=connector_kind,
        url=url,
        status=JOB_PENDING,
        snapshot_id=None,
        error=None,
        attempt=attempt,
        requested_by=requested_by,
        run_at=datetime.now(UTC),
        finished_at=None,
    )
    await unit.job_runs.create(run)
    await unit.outbox.add(
        OutboxEvent(
            event_type=event_type,
            payload={
                "run_id": str(run.id),
                "organization_id": str(project.organization_id),
                "project_id": str(project_id),
            },
        )
    )
    return run


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
) -> JobRun:
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
    _validate_url(url)
    await _check_quota(unit, project.organization_id, project_id, quota)
    run = await _record_run(
        unit,
        project_id=project_id,
        competitor_id=competitor_id,
        connector_kind=connector_kind,
        url=url,
        job_id=None,
        attempt=0,
        requested_by=principal.app_user_id,
        event_type=COLLECTION_JOB_REQUESTED,
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="collection.run",
            target_type="collection_job_run",
            target_id=str(run.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "connector_kind": connector_kind,
                "url": url,
            },
        )
    )
    return run


def normalize_content(content: str) -> str:
    """Canonical form for hashing: surrounding whitespace only — the raw
    payload keeps whatever the server sent (snapshots are raw captures)."""
    return content.strip()


def backoff_seconds(failures: int) -> int:
    """Exponential backoff for a failing schedule: base * 2^(n-1), capped."""
    return min(
        RETRY_BACKOFF_BASE_SECONDS * (2 ** max(failures - 1, 0)),
        RETRY_BACKOFF_CAP_SECONDS,
    )


async def _finish_schedule(
    unit: CollectionUnit, run: JobRun, *, failed: bool
) -> None:
    """Advance the parent schedule after a terminal run result: plain
    interval + failure-streak reset on success, exponential backoff +
    incremented streak on failure. A failed run never deletes or
    reverts snapshots — the schedule simply tries again later."""
    if run.job_id is None:
        return
    job = await unit.jobs.get(run.organization_id, run.project_id, run.job_id)
    if job is None:
        return  # deleted mid-flight; the run still recorded its result
    if failed:
        failures = job.failures + 1
        next_due = datetime.now(UTC) + timedelta(seconds=backoff_seconds(failures))
    else:
        failures = 0
        next_due = datetime.now(UTC) + timedelta(seconds=job.interval_seconds)
    await unit.jobs.advance(
        run.organization_id,
        run.project_id,
        run.job_id,
        next_due_at=next_due,
        failures=failures,
    )


async def _run_job(unit: CollectionUnit, fetcher: WebsiteFetcher, run: JobRun) -> None:
    """One run, failure-isolated: any fetch error marks THIS run failed
    with the error and an audit row, advances the parent schedule into
    backoff, and the drain moves on. The catch is deliberately broad —
    a poison run (buggy adapter included) must never stall the batch or
    roll back other runs' work."""
    try:
        page = await fetcher.fetch(run.url)
    except Exception as exc:
        await unit.job_runs.mark_result(
            run.organization_id,
            run.project_id,
            run.id,
            status=JOB_FAILED,
            snapshot_id=None,
            error=str(exc),
        )
        await _finish_schedule(unit, run, failed=True)
        await unit.audit.record(
            AuditEntry(
                actor_id=run.requested_by,
                action="collection.failed",
                target_type="collection_job_run",
                target_id=str(run.id),
                organization_id=run.organization_id,
                payload={
                    "project_id": str(run.project_id),
                    "job_id": str(run.job_id) if run.job_id else None,
                    "error": str(exc),
                },
            )
        )
        return
    digest = sha256(normalize_content(page.content).encode("utf-8")).hexdigest()
    latest = await unit.snapshots.latest_for_competitor(
        run.organization_id, run.project_id, run.competitor_id, run.connector_kind
    )
    if latest is not None and latest.content_hash == digest:
        await unit.job_runs.mark_result(
            run.organization_id,
            run.project_id,
            run.id,
            status=JOB_UNCHANGED,
            snapshot_id=latest.id,
            error=None,
        )
        await _finish_schedule(unit, run, failed=False)
        await unit.audit.record(
            AuditEntry(
                actor_id=run.requested_by,
                action="collection.unchanged",
                target_type="collection_job_run",
                target_id=str(run.id),
                organization_id=run.organization_id,
                payload={"project_id": str(run.project_id)},
            )
        )
        return
    snapshot = Snapshot(
        id=uuid4(),
        organization_id=run.organization_id,
        project_id=run.project_id,
        competitor_id=run.competitor_id,
        connector_kind=run.connector_kind,
        url=run.url,
        content_hash=digest,
        raw_payload=page.content,
        captured_at=page.fetched_at,
        created_by=run.requested_by,
    )
    await unit.snapshots.create(snapshot)
    await unit.job_runs.mark_result(
        run.organization_id,
        run.project_id,
        run.id,
        status=JOB_SNAPSHOT_CREATED,
        snapshot_id=snapshot.id,
        error=None,
    )
    await _finish_schedule(unit, run, failed=False)
    await unit.outbox.add(
        OutboxEvent(
            event_type=COLLECTION_SNAPSHOT_CREATED,
            payload={
                "snapshot_id": str(snapshot.id),
                "organization_id": str(run.organization_id),
                "project_id": str(run.project_id),
            },
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=run.requested_by,
            action="collection.snapshot_created",
            target_type="collection_snapshot",
            target_id=str(snapshot.id),
            organization_id=run.organization_id,
            payload={"project_id": str(run.project_id)},
        )
    )


async def drain_pending_runs(unit_factory, fetcher: WebsiteFetcher, *, limit: int = 100) -> int:
    """Drain pending runs in ONE transaction, off-request (ADR-004).

    Each run is failure-isolated inside the drain (see _run_job), so one
    bad fetch can never stall or roll back the batch. Tests call this
    directly for determinism; the production poll loop lives in
    infrastructure/dispatcher.py."""
    unit = unit_factory()
    async with unit:
        runs = await unit.job_runs.list_pending(limit=limit)
        for run in runs:
            await _run_job(unit, fetcher, run)
        await unit.commit()
        return len(runs)


# Backwards-compatible alias from ticket #42's naming.
drain_pending_jobs = drain_pending_runs


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
