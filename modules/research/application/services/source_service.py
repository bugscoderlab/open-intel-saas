"""Source use cases (ticket #23, spec #21) — the second research vertical,
shaped after the Notebook service: the scope is derived from the project
row, never from client-supplied IDs; authorization decisions live behind
the matrix; the outbox event goes out in the same transaction as the
source write (plan §14.5).
"""

from dataclasses import replace
from uuid import UUID, uuid4

from modules.platform.application.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry, OutboxEvent
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission
from modules.platform.domain.storage import FileStorage
from modules.research.application.services import file_service
from modules.research.domain.entities import (
    SOURCE_TYPE_FILE,
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


async def create_file_source(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    notebook_id: UUID | None,
    title: str | None,
    filename: str,
    content_type: str,
    data: bytes,
    storage: FileStorage | None,
) -> Source:
    """source.create for an uploaded file (ticket #29): validate (no side
    effects) → Source row → stored object + registry row → submit, one
    transaction. The pipeline never runs in-request (ADR-004): extraction
    lands full_text off-request via the dispatcher.

    The object put happens inside the caller's transaction; if the
    transaction rolls back after the put, a small orphan object can
    remain in the bucket (no reference). That window is accepted here;
    a sweeper is a later operational concern.
    """
    if storage is None:
        raise ServiceUnavailableError("file storage is not configured")
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
    if notebook_id is not None:
        notebook = await unit.notebooks.get(
            project.organization_id, project_id, notebook_id
        )
        if notebook is None:
            raise NotFoundError("notebook not found")
    # Rejected uploads cause no writes at all — validation runs before
    # the source row and the object (file_service validates again inside
    # save_file, cheaply, before its put).
    file_service.validate_upload(filename, content_type, data)
    source = Source(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        notebook_id=notebook_id,
        title=title or filename,
        type=SOURCE_TYPE_FILE,
        status=STATUS_NEW,
        full_text=None,
        error=None,
        created_by=principal.app_user_id,
    )
    await unit.sources.create(source)
    await file_service.save_file(
        unit,
        storage,
        organization_id=project.organization_id,
        project_id=project_id,
        source_id=source.id,
        filename=filename,
        content_type=content_type,
        data=data,
        created_by=principal.app_user_id,
    )
    await _submit(unit, source)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="source.create",
            target_type="source",
            target_id=str(source.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "notebook_id": str(notebook_id) if notebook_id else None,
                "title": title or filename,
                "type": SOURCE_TYPE_FILE,
                "filename": filename,
            },
        )
    )
    return replace(source, status=STATUS_QUEUED)


async def get_file_download_url(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    source_id: UUID,
    storage: FileStorage | None,
) -> str:
    """source.read gating a short-lived signed URL (ticket #29). The URL
    is generated here and now — never read from the database (plan §9.3);
    an unauthorized caller gets the tenant-safe 404 before any signing."""
    if storage is None:
        raise ServiceUnavailableError("file storage is not configured")
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
    if source is None or source.type != SOURCE_TYPE_FILE:
        raise NotFoundError("file source not found")
    registry = await unit.source_files.get_for_source(
        project.organization_id, project_id, source_id
    )
    if registry is None:
        raise NotFoundError("file source not found")
    return await file_service.signed_url_for(storage, registry)
