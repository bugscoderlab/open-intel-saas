"""HTTP routers for the collection module (ticket #42, spec #41).

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
    CollectionRequest,
    JobResponse,
    SnapshotDetailResponse,
    SnapshotResponse,
)
from modules.collection.application.services import collect_service
from modules.collection.domain.entities import (
    CONNECTOR_WEBSITE,
    Job,
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
        status=job.status,
        snapshot_id=job.snapshot_id,
        error=job.error,
        requested_by=job.requested_by,
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
        response_model=JobResponse,
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
    ) -> JobResponse:
        job = await collect_service.request_collection(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            connector_kind=body.connector_kind,
            url=body.url,
            quota=getattr(request.app.state, "collection_quota", None),
        )
        return _job_response(job)

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
