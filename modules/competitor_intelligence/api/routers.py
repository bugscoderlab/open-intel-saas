"""HTTP routers for the competitor-intelligence module.

Routers stay thin: parse, call a service, map typed errors to statuses —
mirroring the platform/research boundary. All authorization decisions
live in the services behind the matrix; no role names here. Response
models are the output allowlist (spec #31).
"""

from uuid import UUID

from fastapi import APIRouter

from modules.competitor_intelligence.api.deps import (
    AuthzDep,
    CompetitorUnitDep,
    PrincipalDep,
)
from modules.competitor_intelligence.api.schemas import (
    CompetitorCreateRequest,
    CompetitorResponse,
    CompetitorUpdateRequest,
    LocationCreateRequest,
    LocationResponse,
    LocationUpdateRequest,
)
from modules.competitor_intelligence.application.services import (
    competitor_service,
    location_service,
)
from modules.competitor_intelligence.domain.entities import Competitor, Location
from modules.platform.api.routers import endpoint


def build_competitors_router() -> APIRouter:
    """Competitor CRUD (ticket #33): project-scoped directory entries."""
    router = APIRouter(tags=["competitors"])

    @router.post(
        "/projects/{project_id}/competitors",
        response_model=CompetitorResponse,
        status_code=201,
    )
    @endpoint
    async def create_competitor(
        project_id: UUID,
        body: CompetitorCreateRequest,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> CompetitorResponse:
        competitor = await competitor_service.create_competitor(
            unit,
            authz,
            principal,
            project_id=project_id,
            name=body.name,
            website=body.website,
            notes=body.notes,
        )
        return _competitor_response(competitor)

    @router.get(
        "/projects/{project_id}/competitors",
        response_model=list[CompetitorResponse],
    )
    @endpoint
    async def list_competitors(
        project_id: UUID,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> list[CompetitorResponse]:
        competitors = await competitor_service.list_competitors(
            unit, authz, principal, project_id=project_id
        )
        return [_competitor_response(c) for c in competitors]

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}",
        response_model=CompetitorResponse,
    )
    @endpoint
    async def get_competitor(
        project_id: UUID,
        competitor_id: UUID,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> CompetitorResponse:
        competitor = await competitor_service.get_competitor(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
        )
        return _competitor_response(competitor)

    @router.patch(
        "/projects/{project_id}/competitors/{competitor_id}",
        response_model=CompetitorResponse,
    )
    @endpoint
    async def update_competitor(
        project_id: UUID,
        competitor_id: UUID,
        body: CompetitorUpdateRequest,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> CompetitorResponse:
        competitor = await competitor_service.update_competitor(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            name=body.name,
            website=body.website,
            notes=body.notes,
        )
        return _competitor_response(competitor)

    @router.delete(
        "/projects/{project_id}/competitors/{competitor_id}", status_code=204
    )
    @endpoint
    async def delete_competitor(
        project_id: UUID,
        competitor_id: UUID,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await competitor_service.delete_competitor(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
        )

    return router


def build_locations_router() -> APIRouter:
    """Location CRUD (ticket #33): branches of a competitor."""
    router = APIRouter(tags=["locations"])

    @router.post(
        "/projects/{project_id}/competitors/{competitor_id}/locations",
        response_model=LocationResponse,
        status_code=201,
    )
    @endpoint
    async def create_location(
        project_id: UUID,
        competitor_id: UUID,
        body: LocationCreateRequest,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> LocationResponse:
        location = await location_service.create_location(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            name=body.name,
            address=body.address,
        )
        return _location_response(location)

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}/locations",
        response_model=list[LocationResponse],
    )
    @endpoint
    async def list_locations(
        project_id: UUID,
        competitor_id: UUID,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> list[LocationResponse]:
        locations = await location_service.list_locations(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
        )
        return [_location_response(loc) for loc in locations]

    @router.get(
        "/projects/{project_id}/competitors/{competitor_id}/locations/{location_id}",
        response_model=LocationResponse,
    )
    @endpoint
    async def get_location(
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> LocationResponse:
        location = await location_service.get_location(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            location_id=location_id,
        )
        return _location_response(location)

    @router.patch(
        "/projects/{project_id}/competitors/{competitor_id}/locations/{location_id}",
        response_model=LocationResponse,
    )
    @endpoint
    async def update_location(
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
        body: LocationUpdateRequest,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> LocationResponse:
        location = await location_service.update_location(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            location_id=location_id,
            name=body.name,
            address=body.address,
        )
        return _location_response(location)

    @router.delete(
        "/projects/{project_id}/competitors/{competitor_id}/locations/{location_id}",
        status_code=204,
    )
    @endpoint
    async def delete_location(
        project_id: UUID,
        competitor_id: UUID,
        location_id: UUID,
        unit: CompetitorUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await location_service.delete_location(
            unit,
            authz,
            principal,
            project_id=project_id,
            competitor_id=competitor_id,
            location_id=location_id,
        )

    return router


def build_competitor_router() -> APIRouter:
    """Everything the competitor module mounts: one router, wired by the
    composition root (serve.py) and the test seam (conftest)."""
    router = APIRouter()
    router.include_router(build_competitors_router())
    router.include_router(build_locations_router())
    return router


def _competitor_response(competitor: Competitor) -> CompetitorResponse:
    return CompetitorResponse(
        id=competitor.id,
        organization_id=competitor.organization_id,
        project_id=competitor.project_id,
        name=competitor.name,
        website=competitor.website,
        notes=competitor.notes,
    )


def _location_response(location: Location) -> LocationResponse:
    return LocationResponse(
        id=location.id,
        organization_id=location.organization_id,
        project_id=location.project_id,
        competitor_id=location.competitor_id,
        name=location.name,
        address=location.address,
    )
