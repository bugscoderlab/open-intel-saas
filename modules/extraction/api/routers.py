"""HTTP routers for the extraction module (ticket #50, spec #47).

Thin router: parse, call the service, map typed errors to statuses.
POST only enqueues (run row + outbox event in one transaction, 202);
the dispatcher drains off-request (ADR-004) and records proposed
observations through the sink port. Authorization lives in the service
behind the matrix.
"""

from uuid import UUID

from fastapi import APIRouter, Request

from modules.extraction.api.deps import (
    AuthzDep,
    ExtractionUnitDep,
    PrincipalDep,
    SnapshotSourceDep,
)
from modules.extraction.api.schemas import ExtractionRunResponse
from modules.extraction.application.services import extract_service
from modules.extraction.domain.entities import ExtractionRun
from modules.platform.api.routers import endpoint


def _run_response(run: ExtractionRun) -> ExtractionRunResponse:
    return ExtractionRunResponse(
        id=run.id,
        organization_id=run.organization_id,
        project_id=run.project_id,
        competitor_id=run.competitor_id,
        snapshot_id=run.snapshot_id,
        status=run.status,
        extraction_version=run.extraction_version,
        error=run.error,
    )


def build_extraction_router() -> APIRouter:
    router = APIRouter(tags=["extraction"])

    @router.post(
        "/projects/{project_id}/competitors/{competitor_id}"
        "/snapshots/{snapshot_id}/extract",
        response_model=ExtractionRunResponse,
        status_code=202,
    )
    @endpoint
    async def request_extraction(
        project_id: UUID,
        competitor_id: UUID,
        snapshot_id: UUID,
        request: Request,
        unit: ExtractionUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        snapshot_source: SnapshotSourceDep,
    ) -> ExtractionRunResponse:
        run = await extract_service.request_extraction(
            unit,
            authz,
            principal,
            snapshot_source,
            project_id=project_id,
            competitor_id=competitor_id,
            snapshot_id=snapshot_id,
        )
        return _run_response(run)

    return router
