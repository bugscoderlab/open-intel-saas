"""Discovery use case (ticket #43, spec #41) — the maps slice.

Discovery returns candidate businesses as DATA and persists nothing:
adding a candidate stays the Phase 3 manual competitor flow (spec #41
assumption 3, deliberate and reversible). The maps provider is a domain
port; a failing provider raises typed errors that never touch website
collection — the connectors are independent (user story 5).
"""

from uuid import UUID

from modules.collection.domain.ports import MapCandidate, MapsProvider
from modules.collection.domain.unit_of_work import CollectionUnit
from modules.platform.application.errors import NotFoundError, ValidationError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def discover_businesses(
    unit: CollectionUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    query: str,
    location: str,
    provider: MapsProvider,
) -> list[MapCandidate]:
    """collection.run — discover candidate competitors through the maps
    provider; nothing is written but the audit row (the query spends
    provider quota, so it is recorded like a mutation)."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.COLLECTION_RUN,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    query = query.strip()
    location = location.strip()
    if not query:
        raise ValidationError("query must not be empty")
    if not location:
        raise ValidationError("location must not be empty")
    candidates = await provider.discover(query=query, location=location)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="collection.discover",
            target_type="collection_discovery",
            target_id=str(project_id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "query": query,
                "location": location,
                "candidates": len(candidates),
            },
        )
    )
    return candidates
