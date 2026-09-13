"""Notebook use cases (ticket #22, spec #21) — the research module's first
vertical, deliberately shaped after the Project tag service: repositories
filter by the explicit tenant scope on every query; the service derives
that scope from the project row, never from client-supplied IDs.
"""

from uuid import UUID, uuid4

from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission
from modules.research.domain.entities import Notebook
from modules.research.domain.unit_of_work import ResearchUnit


async def _load_project_scope(unit: ResearchUnit, project_id: UUID):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    return project


async def create_notebook(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    name: str,
    description: str | None = None,
) -> Notebook:
    """notebook.create at the project's scope; the row carries both keys."""
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.NOTEBOOK_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    notebook = Notebook(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        name=name,
        description=description,
        archived=False,
        created_by=principal.app_user_id,
    )
    await unit.notebooks.create(notebook)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="notebook.create",
            target_type="notebook",
            target_id=str(notebook.id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": name},
        )
    )
    return notebook


async def list_notebooks(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[Notebook]:
    """notebook.read at the project's scope."""
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.NOTEBOOK_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.notebooks.list_for_project(
        project.organization_id, project_id
    )


async def update_notebook(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
    name: str | None = None,
    description: str | None = None,
    archived: bool | None = None,
) -> Notebook:
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.NOTEBOOK_UPDATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    notebook = await unit.notebooks.get(
        project.organization_id, project_id, notebook_id
    )
    if notebook is None:
        raise NotFoundError("notebook not found")
    updated = Notebook(
        id=notebook.id,
        organization_id=notebook.organization_id,
        project_id=notebook.project_id,
        name=name if name is not None else notebook.name,
        description=description if description is not None else notebook.description,
        archived=archived if archived is not None else notebook.archived,
        created_by=notebook.created_by,
    )
    await unit.notebooks.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="notebook.update",
            target_type="notebook",
            target_id=str(notebook_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": updated.name},
        )
    )
    return updated


async def delete_notebook(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
) -> None:
    project = await _load_project_scope(unit, project_id)
    await authz.require(
        principal,
        Permission.NOTEBOOK_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if (
        await unit.notebooks.get(project.organization_id, project_id, notebook_id)
        is None
    ):
        raise NotFoundError("notebook not found")
    await unit.notebooks.delete(project.organization_id, project_id, notebook_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="notebook.delete",
            target_type="notebook",
            target_id=str(notebook_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
