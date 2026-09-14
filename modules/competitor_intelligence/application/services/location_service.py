"""Location use cases (ticket #33, spec #31) — scoped through the owning
competitor row: the project authorizes, the competitor row (already
tenant-scoped) provides the write scope. Text sanitized on write.
"""

from uuid import UUID, uuid4

from modules.competitor_intelligence.domain.entities import Location
from modules.competitor_intelligence.domain.text import sanitize_optional, sanitize_text
from modules.competitor_intelligence.domain.unit_of_work import CompetitorUnit
from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def _load_competitor_scope(
    unit: CompetitorUnit, project_id: UUID, competitor_id: UUID
):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    competitor = await unit.competitors.get(
        project.organization_id, project_id, competitor_id
    )
    if competitor is None:
        raise NotFoundError("competitor not found")
    return project, competitor


async def create_location(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    name: str,
    address: str | None = None,
) -> Location:
    """location.create — the row carries the competitor's tenant scope."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.LOCATION_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    location = Location(
        id=uuid4(),
        organization_id=competitor.organization_id,
        project_id=project_id,
        competitor_id=competitor_id,
        name=sanitize_text(name, max_length=500),
        address=sanitize_optional(address),
        created_by=principal.app_user_id,
    )
    await unit.locations.create(location)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="location.create",
            target_type="location",
            target_id=str(location.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
            },
        )
    )
    return location


async def list_locations(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
) -> list[Location]:
    """location.read at the competitor's scope."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.LOCATION_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.locations.list_for_competitor(
        competitor.organization_id, project_id, competitor_id
    )


async def get_location(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    location_id: UUID,
) -> Location:
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.LOCATION_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    location = await unit.locations.get(
        competitor.organization_id, project_id, competitor_id, location_id
    )
    if location is None:
        raise NotFoundError("location not found")
    return location


async def update_location(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    location_id: UUID,
    name: str | None = None,
    address: str | None = None,
) -> Location:
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.LOCATION_UPDATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    location = await unit.locations.get(
        competitor.organization_id, project_id, competitor_id, location_id
    )
    if location is None:
        raise NotFoundError("location not found")
    updated = Location(
        id=location.id,
        organization_id=location.organization_id,
        project_id=location.project_id,
        competitor_id=location.competitor_id,
        name=sanitize_text(name, max_length=500) if name is not None else location.name,
        address=sanitize_optional(address) if address is not None else location.address,
        created_by=location.created_by,
    )
    await unit.locations.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="location.update",
            target_type="location",
            target_id=str(location_id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
            },
        )
    )
    return updated


async def delete_location(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    location_id: UUID,
) -> None:
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.LOCATION_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if (
        await unit.locations.get(
            competitor.organization_id, project_id, competitor_id, location_id
        )
        is None
    ):
        raise NotFoundError("location not found")
    await unit.locations.delete(
        competitor.organization_id, project_id, competitor_id, location_id
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="location.delete",
            target_type="location",
            target_id=str(location_id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
            },
        )
    )
