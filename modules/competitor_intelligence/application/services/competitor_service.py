"""Competitor use cases (ticket #33, spec #31) — shaped after the
research services: the scope is derived from the project row, never from
client-supplied IDs; authorization decisions live behind the matrix;
every user-supplied text field is sanitized before persistence (spec #31
requirement). Route code checks no role names.
"""

from uuid import UUID, uuid4

from modules.competitor_intelligence.domain.entities import Competitor
from modules.competitor_intelligence.domain.text import sanitize_optional, sanitize_text
from modules.competitor_intelligence.domain.unit_of_work import CompetitorUnit
from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def create_competitor(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    name: str,
    website: str | None = None,
    notes: str | None = None,
) -> Competitor:
    """competitor.create at the project's scope."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.COMPETITOR_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    competitor = Competitor(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        name=sanitize_text(name, max_length=500),
        website=sanitize_optional(website, max_length=2000),
        notes=sanitize_optional(notes),
        created_by=principal.app_user_id,
    )
    await unit.competitors.create(competitor)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="competitor.create",
            target_type="competitor",
            target_id=str(competitor.id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": competitor.name},
        )
    )
    return competitor


async def list_competitors(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[Competitor]:
    """competitor.read at the project's scope."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.COMPETITOR_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.competitors.list_for_project(
        project.organization_id, project_id
    )


async def get_competitor(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
) -> Competitor:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.COMPETITOR_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    competitor = await unit.competitors.get(
        project.organization_id, project_id, competitor_id
    )
    if competitor is None:
        raise NotFoundError("competitor not found")
    return competitor


async def update_competitor(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    name: str | None = None,
    website: str | None = None,
    notes: str | None = None,
) -> Competitor:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.COMPETITOR_UPDATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    competitor = await unit.competitors.get(
        project.organization_id, project_id, competitor_id
    )
    if competitor is None:
        raise NotFoundError("competitor not found")
    updated = Competitor(
        id=competitor.id,
        organization_id=competitor.organization_id,
        project_id=competitor.project_id,
        name=sanitize_text(name, max_length=500) if name is not None else competitor.name,
        website=(
            sanitize_optional(website, max_length=2000)
            if website is not None
            else competitor.website
        ),
        notes=sanitize_optional(notes) if notes is not None else competitor.notes,
        created_by=competitor.created_by,
    )
    await unit.competitors.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="competitor.update",
            target_type="competitor",
            target_id=str(competitor_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": updated.name},
        )
    )
    return updated


async def delete_competitor(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
) -> None:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.COMPETITOR_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if (
        await unit.competitors.get(project.organization_id, project_id, competitor_id)
        is None
    ):
        raise NotFoundError("competitor not found")
    await unit.competitors.delete(project.organization_id, project_id, competitor_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="competitor.delete",
            target_type="competitor",
            target_id=str(competitor_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
