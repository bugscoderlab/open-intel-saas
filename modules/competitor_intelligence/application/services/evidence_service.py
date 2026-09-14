"""Evidence use cases (ticket #35, spec #31) — the competitor↔research
connection (glossary: Evidence).

Links point at research rows by opaque UUID: this module never imports
research and never validates target existence (plan §14.4 rule 2).
Cross-module existence validation is deliberately deferred until
Phase 5, behind the module-enabled check (spec #31 assumption 4) — the
Phase 5 crawler attaches evidence it created itself, so the check will
live next to the collection flow.
"""

from uuid import UUID, uuid4

from modules.competitor_intelligence.domain.entities import (
    EVIDENCE_TARGET_KINDS,
    OBSERVATION_APPROVED,
    EvidenceLink,
)
from modules.competitor_intelligence.domain.text import sanitize_text
from modules.competitor_intelligence.domain.unit_of_work import CompetitorUnit
from modules.platform.application.errors import NotFoundError, ValidationError
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


async def add_evidence(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    target_kind: str,
    target_id: UUID,
    observation_id: UUID | None,
    excerpt: str | None,
    excerpt_start: int | None,
    excerpt_end: int | None,
) -> EvidenceLink:
    """evidence.create — a manual attach is trusted, so it lands
    approved immediately (states are retained for Phase 5 automation).
    Referenced observation, when given, must belong to this competitor
    in this scope."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.EVIDENCE_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if target_kind not in EVIDENCE_TARGET_KINDS:
        raise ValidationError(f"target_kind must be one of {EVIDENCE_TARGET_KINDS}")
    if excerpt_start is not None and excerpt_end is not None:
        if excerpt_end < excerpt_start:
            raise ValidationError("excerpt_end must be >= excerpt_start")
    if observation_id is not None:
        observation = await unit.observations.get(
            project.organization_id, project_id, observation_id
        )
        if observation is None or observation.competitor_id != competitor_id:
            raise NotFoundError("observation not found")
    link = EvidenceLink(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        competitor_id=competitor_id,
        observation_id=observation_id,
        target_kind=target_kind,
        target_id=target_id,
        excerpt=sanitize_text(excerpt) if excerpt is not None else None,
        excerpt_start=excerpt_start,
        excerpt_end=excerpt_end,
        approval_state=OBSERVATION_APPROVED,
        created_by=principal.app_user_id,
    )
    await unit.evidence.create(link)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="evidence.create",
            target_type="evidence_link",
            target_id=str(link.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "target_kind": target_kind,
            },
        )
    )
    return link


async def list_evidence(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    target_kind: str | None = None,
    observation_id: UUID | None = None,
) -> list[EvidenceLink]:
    """evidence.read — scoped through the competitor; filterable by
    target kind and by the observation a link supports."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.EVIDENCE_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.evidence.list_for_competitor(
        project.organization_id,
        project_id,
        competitor_id,
        target_kind=target_kind,
        observation_id=observation_id,
    )


async def delete_evidence(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    evidence_id: UUID,
) -> None:
    """evidence.delete — removes the link only; the research target row
    is owned by the research module and is never touched from here."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.EVIDENCE_DELETE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    link = await unit.evidence.get(
        project.organization_id, project_id, competitor_id, evidence_id
    )
    if link is None:
        raise NotFoundError("evidence link not found")
    await unit.evidence.delete(
        project.organization_id, project_id, competitor_id, evidence_id
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="evidence.delete",
            target_type="evidence_link",
            target_id=str(evidence_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
