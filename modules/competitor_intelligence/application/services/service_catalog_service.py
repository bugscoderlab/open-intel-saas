"""Service-catalog use cases (ticket #34, spec #31) — the canonical
offering list per Project (glossary). Names dedupe case-insensitively;
a service referenced by observations cannot be deleted (the observations
keep their grouping key — plan §14.4 keeps module rows stable).
"""

from uuid import UUID, uuid4

from modules.competitor_intelligence.domain.entities import Service
from modules.competitor_intelligence.domain.text import sanitize_text
from modules.competitor_intelligence.domain.unit_of_work import CompetitorUnit
from modules.platform.application.errors import ConflictError, NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def _load_project(unit: CompetitorUnit, project_id: UUID):
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    return project


async def create_service(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    name: str,
) -> Service:
    """service.create — duplicate names (any case) are a 409."""
    project = await _load_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SERVICE_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    cleaned = sanitize_text(name, max_length=500)
    existing = await unit.services.get_by_name(
        project.organization_id, project_id, cleaned
    )
    if existing is not None:
        raise ConflictError(f"service '{cleaned}' already exists in this project")
    service = Service(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        name=cleaned,
        created_by=principal.app_user_id,
    )
    await unit.services.create(service)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="service.create",
            target_type="service",
            target_id=str(service.id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id), "name": cleaned},
        )
    )
    return service


async def list_services(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[Service]:
    project = await _load_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SERVICE_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.services.list_for_project(project.organization_id, project_id)


async def delete_service(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    service_id: UUID,
) -> None:
    project = await _load_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SERVICE_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    service = await unit.services.get(project.organization_id, project_id, service_id)
    if service is None:
        raise NotFoundError("service not found")
    referencing = await unit.observations.count_referencing_service(
        project.organization_id, project_id, service_id
    )
    if referencing > 0:
        raise ConflictError(
            "service is referenced by observations and cannot be deleted"
        )
    await unit.services.delete(project.organization_id, project_id, service_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="service.delete",
            target_type="service",
            target_id=str(service_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
