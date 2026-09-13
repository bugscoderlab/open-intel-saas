"""Note use cases (ticket #30, spec #26) — shaped after the Notebook
service: repositories filter by the explicit tenant scope plus the
owning notebook on every query; the service derives that scope from the
notebook row, never from client-supplied IDs; route code checks no role
names — the matrix answers every authorization question.
"""

from uuid import UUID, uuid4

from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission
from modules.research.domain.entities import Note
from modules.research.domain.unit_of_work import ResearchUnit


async def _load_notebook_scope(
    unit: ResearchUnit, project_id: UUID, notebook_id: UUID
):
    """The scope rule (mirrors source_service): the project row authorizes,
    the notebook row (already tenant-scoped) provides the write scope."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    notebook = await unit.notebooks.get(
        project.organization_id, project_id, notebook_id
    )
    if notebook is None:
        raise NotFoundError("notebook not found")
    return project, notebook


async def create_note(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
    title: str,
    content: str = "",
) -> Note:
    """note.create — the row carries the notebook's tenant scope."""
    project, notebook = await _load_notebook_scope(unit, project_id, notebook_id)
    await authz.require(
        principal,
        Permission.NOTE_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    note = Note(
        id=uuid4(),
        organization_id=notebook.organization_id,
        project_id=project_id,
        notebook_id=notebook_id,
        title=title,
        content=content,
        created_by=principal.app_user_id,
    )
    await unit.notes.create(note)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="note.create",
            target_type="note",
            target_id=str(note.id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "notebook_id": str(notebook_id)},
        )
    )
    return note


async def list_notes(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
) -> list[Note]:
    """note.read at the notebook's scope."""
    project, notebook = await _load_notebook_scope(unit, project_id, notebook_id)
    await authz.require(
        principal,
        Permission.NOTE_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.notes.list_for_notebook(
        notebook.organization_id, project_id, notebook_id
    )


async def get_note(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
    note_id: UUID,
) -> Note:
    """note.read — single row."""
    project, notebook = await _load_notebook_scope(unit, project_id, notebook_id)
    await authz.require(
        principal,
        Permission.NOTE_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    note = await unit.notes.get(
        notebook.organization_id, project_id, notebook_id, note_id
    )
    if note is None:
        raise NotFoundError("note not found")
    return note


async def update_note(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
    note_id: UUID,
    title: str | None = None,
    content: str | None = None,
) -> Note:
    project, notebook = await _load_notebook_scope(unit, project_id, notebook_id)
    await authz.require(
        principal,
        Permission.NOTE_UPDATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    note = await unit.notes.get(
        notebook.organization_id, project_id, notebook_id, note_id
    )
    if note is None:
        raise NotFoundError("note not found")
    updated = Note(
        id=note.id,
        organization_id=note.organization_id,
        project_id=note.project_id,
        notebook_id=note.notebook_id,
        title=title if title is not None else note.title,
        content=content if content is not None else note.content,
        created_by=note.created_by,
    )
    await unit.notes.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="note.update",
            target_type="note",
            target_id=str(note_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "notebook_id": str(notebook_id)},
        )
    )
    return updated


async def delete_note(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
    note_id: UUID,
) -> None:
    project, notebook = await _load_notebook_scope(unit, project_id, notebook_id)
    await authz.require(
        principal,
        Permission.NOTE_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if (
        await unit.notes.get(notebook.organization_id, project_id, notebook_id, note_id)
        is None
    ):
        raise NotFoundError("note not found")
    await unit.notes.delete(
        notebook.organization_id, project_id, notebook_id, note_id
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="note.delete",
            target_type="note",
            target_id=str(note_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "notebook_id": str(notebook_id)},
        )
    )
