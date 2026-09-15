"""HTTP routers for the collection module (tickets #42/#43/#44, spec #41).

Routers stay thin: parse, call a service, map typed errors to statuses —
mirroring the platform/research/competitor boundary. All authorization
decisions live in the services behind the matrix; no role names here.

The fetcher never appears here: POST only enqueues (job + outbox event,
202); the dispatcher drains off-request (ADR-004). The per-project fetch
quota rides on ``app.state.collection_quota`` (set by the composition
root from settings; tests set it directly) — None means unlimited.
"""

from uuid import UUID

from fastapi import APIRouter, Request

from modules.collection.api.deps import (
    AuthzDep,
    CollectionUnitDep,
    PrincipalDep,
)
from modules.collection.api.schemas import (
    CandidateResponse,
    CollectionRequest,
    DiscoverRequest,
    JobCreateRequest,
    JobResponse,
    JobRunResponse,
    SnapshotDetailResponse,
    SnapshotResponse,
)
from modules.collection.application.services import (
    collect_service,
    discovery_service,
    job_service,
)
from modules.collection.domain.entities import (
    CONNECTOR_WEBSITE,
    Job,
    JobRun,
    Snapshot,
)
from modules.platform.api.routers import endpoint


def _job_response(job: Job) -> JobResponse:
    return JobResponse(
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
        created_by=job.created_by,
    )


def _run_response(run: JobRun) -> JobRunResponse:
    return JobRunResponse(
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


def _snapshot_response(snapshot: Snapshot) -> SnapshotResponse:
    return SnapshotResponse(
        id=snapshot.id,
        organization_id=snapshot.organization_id,
        project_id=snapshot.project_id,
        competitor_id=snapshot.competitor_id,
        connector_kind=snapshot.connector_kind,
        url=snapshot.url,
        content_hash=snapshot.content_hash,
        captured_at=snapshot.captured_at,
    )


def build_collection_router() -> APIRouter:
    """On-demand collection + snapshot reads (ticket #42)."""
    router = APIRouter(tags=["collection"])

    @router.post(
        "/projects/{project_id}/competitors/{competitor_id}/collections",
        response_model=JobRunResponse,
        status_code=202,
    )
    @endpoint
    async def request_collection(
        project_id: UUID,
        competitor_id: UUID,
        body: CollectionRequest,
        request: Request,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> JobRunResponse:
        run = await collect_service.request_collection(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            connector_kind=body.connector_kind,
            url=body.url,
            quota=getattr(request.app.state, "collection_quota", None),
        )
        return _run_response(run)

    @router.post(
        "/projects/{project_id}/competitors/{competitor_id}/jobs",
        response_model=JobResponse,
        status_code=201,
    )
    @endpoint
    async def create_job(
        project_id: UUID,
        competitor_id: UUID,
        body: JobCreateRequest,
        request: Request,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> JobResponse:
        job = await job_service.create_job(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            connector_kind=body.connector_kind,
            url=body.url,
            interval_seconds=body.interval_seconds,
            quota=getattr(request.app.state, "collection_quota", None),
        )
        return _job_response(job)

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}/jobs",
        response_model=list[JobResponse],
    )
    @endpoint
    async def list_jobs(
        project_id: UUID,
        competitor_id: UUID,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> list[JobResponse]:
        jobs = await job_service.list_jobs(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
        )
        return [_job_response(j) for j in jobs]

    @router.delete(
        "/projects/{project_id}/competitors/{competitor_id}/jobs/{job_id}",
        status_code=204,
    )
    @endpoint
    async def delete_job(
        project_id: UUID,
        competitor_id: UUID,
        job_id: UUID,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await job_service.delete_job(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            job_id=job_id,
        )

    @router.post(
        "/projects/{project_id}/competitors/{competitor_id}/jobs/{job_id}/run",
        response_model=JobRunResponse,
        status_code=202,
    )
    @endpoint
    async def run_job_now(
        project_id: UUID,
        competitor_id: UUID,
        job_id: UUID,
        request: Request,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> JobRunResponse:
        run = await job_service.run_job_now(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            job_id=job_id,
            quota=getattr(request.app.state, "collection_quota", None),
        )
        return _run_response(run)

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}/jobs/{job_id}/runs",
        response_model=list[JobRunResponse],
    )
    @endpoint
    async def list_runs(
        project_id: UUID,
        competitor_id: UUID,
        job_id: UUID,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> list[JobRunResponse]:
        runs = await job_service.list_runs(
            unit,
            authz,
            principal,
            project_id=project_id,
            job_id=job_id,
        )
        return [_run_response(r) for r in runs]

    @router.post(
        "/projects/{project_id}/discover",
        response_model=list[CandidateResponse],
        status_code=200,
    )
    @endpoint
    async def discover_businesses(
        project_id: UUID,
        body: DiscoverRequest,
        request: Request,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> list[CandidateResponse]:
        from modules.collection.domain.errors import MapsConfigurationError

        provider = getattr(request.app.state, "collection_maps_provider", None)
        if provider is None:
            # Wired off (tests/embedded apps): fail visible and typed,
            # exactly like an unconfigured provider would.
            raise MapsConfigurationError("maps provider is not configured")
        candidates = await discovery_service.discover_businesses(
            unit,
            authz,
            principal,
            project_id=project_id,
            query=body.query,
            location=body.location,
            provider=provider,
        )
        return [CandidateResponse.model_validate(c) for c in candidates]

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}/snapshots",
        response_model=list[SnapshotResponse],
    )
    @endpoint
    async def list_snapshots(
        project_id: UUID,
        competitor_id: UUID,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> list[SnapshotResponse]:
        snapshots = await collect_service.list_snapshots(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            connector_kind=CONNECTOR_WEBSITE,
        )
        return [_snapshot_response(s) for s in snapshots]

    @router.get(
        "/projects/{project_id}/snapshots/{snapshot_id}",
        response_model=SnapshotDetailResponse,
    )
    @endpoint
    async def get_snapshot(
        project_id: UUID,
        snapshot_id: UUID,
        unit: CollectionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> SnapshotDetailResponse:
        snapshot = await collect_service.get_snapshot(
            unit,
            authz,
            principal,
            project_id=project_id,
            snapshot_id=snapshot_id,
        )
        return SnapshotDetailResponse(
            **_snapshot_response(snapshot).model_dump(), raw_payload=snapshot.raw_payload
        )

    return router
