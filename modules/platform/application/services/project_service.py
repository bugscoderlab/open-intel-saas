"""Project use cases (ticket #7). A Project belongs directly to an
Organization and optionally to a Team, with a visibility setting. The
creator gets an explicit editor membership; team-derived access flows
through the matrix at check time.
"""

from uuid import UUID, uuid4

from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.entities import (
    AuditEntry,
    Project,
    ProjectMembership,
)
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission

VISIBILITIES = frozenset({"private", "team", "organization"})


async def create_project(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
    name: str,
    owning_team_id: UUID | None = None,
    visibility: str = "private",
) -> Project:
    """Create a Project (organization-owned or team-owned)."""
    await authz.require(
        principal, Permission.PROJECT_CREATE, organization_id=organization_id
    )
    if visibility not in VISIBILITIES:
        raise NotFoundError("unknown visibility")
    if owning_team_id is not None:
        team = await unit.teams.get(owning_team_id)
        if team is None or team.organization_id != organization_id:
            raise NotFoundError("team not found")
    project = Project(
        id=uuid4(),
        organization_id=organization_id,
        owning_team_id=owning_team_id,
        name=name,
        visibility=visibility,
        created_by=principal.app_user_id,
    )
    await unit.projects.create(project)
    await unit.project_memberships.add(
        ProjectMembership(
            project_id=project.id, app_user_id=principal.app_user_id, role="editor"
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="project.create",
            target_type="project",
            target_id=str(project.id),
            organization_id=organization_id,
            payload={
                "name": name,
                "owning_team_id": str(owning_team_id) if owning_team_id else None,
                "visibility": visibility,
            },
        )
    )
    return project


async def list_projects(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
) -> list[Project]:
    await authz.require(principal, Permission.ORG_READ, organization_id=organization_id)
    return await unit.projects.list_for_organization(organization_id)


async def get_project(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> Project:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.PROJECT_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return project


async def update_project(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    name: str | None = None,
    visibility: str | None = None,
) -> Project:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.PROJECT_UPDATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if visibility is not None and visibility not in VISIBILITIES:
        raise NotFoundError("unknown visibility")
    updated = Project(
        id=project.id,
        organization_id=project.organization_id,
        owning_team_id=project.owning_team_id,
        name=name if name is not None else project.name,
        visibility=visibility if visibility is not None else project.visibility,
        created_by=project.created_by,
    )
    await unit.projects.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="project.update",
            target_type="project",
            target_id=str(project_id),
            organization_id=project.organization_id,
            payload={"name": updated.name, "visibility": updated.visibility},
        )
    )
    return updated


async def delete_project(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> None:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.PROJECT_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    await unit.projects.delete(project_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="project.delete",
            target_type="project",
            target_id=str(project_id),
            organization_id=project.organization_id,
            payload={},
        )
    )


async def list_project_members(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[ProjectMembership]:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.PROJECT_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.project_memberships.list(project_id)


async def remove_project_member(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    target_app_user_id: UUID,
) -> None:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.PROJECT_MEMBER_REMOVE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    target = await unit.project_memberships.get(project_id, target_app_user_id)
    if target is None:
        raise NotFoundError("project member not found")
    await unit.project_memberships.remove(project_id, target_app_user_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="project.member_remove",
            target_type="project_member",
            target_id=str(target_app_user_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
