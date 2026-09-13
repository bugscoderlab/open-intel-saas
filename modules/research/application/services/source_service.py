"""Source use cases (ticket #23, spec #21) — the second research vertical,
shaped after the Notebook service: the scope is derived from the project
row, never from client-supplied IDs; authorization decisions live behind
the matrix; the outbox event goes out in the same transaction as the
source write (plan §14.5).
"""

from dataclasses import replace
from uuid import UUID, uuid4

from modules.platform.application.errors import ConflictError, NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry, OutboxEvent
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission
from modules.research.domain.entities import (
    SOURCE_TYPE_TEXT,
    STATUS_FAILED,
    STATUS_NEW,
    STATUS_QUEUED,
    Source,
)
from modules.research.domain.events import SOURCE_SUBMITTED
from modules.research.domain.unit_of_work import ResearchUnit

# A source can be re-driven while it has not reached a terminal/active
# state; "running" is owned by the dispatcher, "completed" by success.
RETRYABLE_STATUSES = (STATUS_NEW, STATUS_QUEUED, STATUS_FAILED)


async def _submit(unit: ResearchUnit, source: Source) -> None:
    """Queue the async pipeline: status flip + outbox event, same
    transaction as whatever write preceded the call."""
    await unit.sources.update_status(
        source.organization_id,
        source.project_id,
        source.id,
        status=STATUS_QUEUED,
        error=None,
    )
    await unit.outbox.add(
        OutboxEvent(
            event_type=SOURCE_SUBMITTED,
            payload={
                "source_id": str(source.id),
                "organization_id": str(source.organization_id),
                "project_id": str(source.project_id),
                "notebook_id": (
                    str(source.notebook_id) if source.notebook_id else None
                ),
            },
        )
    )


async def create_text_source(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID,
    title: str,
    content: str,
) -> Source:
    """source.create at the project's scope; the row lands in "queued" and
    the pipeline never runs in-request (ADR-004)."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.SOURCE_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    notebook = await unit.notebooks.get(
        project.organization_id, project_id, notebook_id
    )
    if notebook is None:
        raise NotFoundError("notebook not found")
    source = Source(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        notebook_id=notebook_id,
        title=title,
        type=SOURCE_TYPE_TEXT,
        status=STATUS_QUEUED,
        full_text=content,
        error=None,
        created_by=principal.app_user_id,
    )
    await unit.sources.create(source)
    await _submit(unit, source)  # idempotent with the row's initial state
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="source.create",
            target_type="source",
            target_id=str(source.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "notebook_id": str(notebook_id),
                "title": title,
                "type": SOURCE_TYPE_TEXT,
            },
        )
    )
    return source


async def list_sources(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[Source]:
    """source.read at the project's scope."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.SOURCE_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.sources.list_for_project(
        project.organization_id, project_id
    )


async def get_source(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    source_id: UUID,
) -> Source:
    """source.read — this is the status poll endpoint."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.SOURCE_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    source = await unit.sources.get(
        project.organization_id, project_id, source_id
    )
    if source is None:
        raise NotFoundError("source not found")
    return source


async def retry_source(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    source_id: UUID,
) -> Source:
    """source.retry: re-queue a stuck or failed source. Emits a fresh
    SourceSubmitted event; the pipeline's delete-and-reinsert chunking
    makes repeated execution idempotent."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.SOURCE_RETRY,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    source = await unit.sources.get(
        project.organization_id, project_id, source_id
    )
    if source is None:
        raise NotFoundError("source not found")
    if source.status not in RETRYABLE_STATUSES:
        raise ConflictError(f"source is not retryable from {source.status}")
    await _submit(unit, source)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="source.retry",
            target_type="source",
            target_id=str(source_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
    return replace(source, status=STATUS_QUEUED, error=None)
