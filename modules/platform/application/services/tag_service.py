"""Project tag use cases (ticket #8) — the trivial tenant-owned entity
proving the scoping pattern. Repositories filter by the explicit tenant
scope on every query; the service derives that scope from the project row,
never from client-supplied IDs.
"""

from uuid import UUID, uuid4

from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.entities import AuditEntry, ProjectTag
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def _load_project_scope(unit: PlatformUnit, project_id: UUID):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    return project


async def create_tag(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    name: str,
    color: str | None = None,
) -> ProjectTag:
    """tag.create at the project's scope; the row carries both tenant keys."""
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.TAG_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    tag = ProjectTag(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        name=name,
        color=color,
        created_by=principal.app_user_id,
    )
    await unit.tags.create(tag)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="tag.create",
            target_type="project_tag",
            target_id=str(tag.id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": name},
        )
    )
    return tag


async def list_tags(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[ProjectTag]:
    """tag.read at the project's scope."""
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.TAG_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.tags.list_for_project(project.organization_id, project_id)


async def update_tag(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    tag_id: UUID,
    name: str | None = None,
    color: str | None = None,
) -> ProjectTag:
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.TAG_UPDATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    tag = await unit.tags.get(project.organization_id, project_id, tag_id)
    if tag is None:
        raise NotFoundError("tag not found")
    updated = ProjectTag(
        id=tag.id,
        organization_id=tag.organization_id,
        project_id=tag.project_id,
        name=name if name is not None else tag.name,
        color=color if color is not None else tag.color,
        created_by=tag.created_by,
    )
    await unit.tags.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="tag.update",
            target_type="project_tag",
            target_id=str(tag_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": updated.name},
        )
    )
    return updated


async def delete_tag(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    tag_id: UUID,
) -> None:
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.TAG_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if await unit.tags.get(project.organization_id, project_id, tag_id) is None:
        raise NotFoundError("tag not found")
    await unit.tags.delete(project.organization_id, project_id, tag_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="tag.delete",
            target_type="project_tag",
            target_id=str(tag_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
