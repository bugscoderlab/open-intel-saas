"""Observation use cases (ticket #34, spec #31) — the manual review flow
(glossary: Review queue). Facts are stored, never overwritten: approving
a different value for the same (competitor, service, location, kind)
supersedes the prior approved row and emits CompetitorChangeDetected in
the same transaction (glossary: Change); an identical re-observation is
not a Change. Rejected rows are retained for audit.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from modules.competitor_intelligence.domain.entities import (
    KIND_PRICE,
    MANUAL_CONFIDENCE,
    MANUAL_EXTRACTION_VERSION,
    OBSERVATION_APPROVED,
    OBSERVATION_PENDING,
    OBSERVATION_REJECTED,
    Observation,
)
from modules.competitor_intelligence.domain.events import COMPETITOR_CHANGE_DETECTED
from modules.competitor_intelligence.domain.unit_of_work import CompetitorUnit
from modules.platform.application.errors import ConflictError, NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry, OutboxEvent
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


def _same_group(a: Observation, b: Observation) -> bool:
    """Same comparison cell: (competitor, service, location, kind) —
    NULLs compare as equal (a market-level fact has no location)."""
    return (
        a.competitor_id == b.competitor_id
        and a.service_id == b.service_id
        and a.location_id == b.location_id
        and a.kind == b.kind
    )


def _same_value(a: Observation, b: Observation) -> bool:
    if a.kind == KIND_PRICE:
        return (
            a.price_amount == b.price_amount
            and (a.price_currency or "") == (b.price_currency or "")
        )
    return False


async def create_observation(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
    service_id: UUID | None,
    location_id: UUID | None,
    price_amount: Decimal,
    price_currency: str,
    observed_on: date,
    kind: str = KIND_PRICE,
) -> Observation:
    """observation.create — manual entries land pending and wait in the
    review queue. Referenced service/location (when given) must exist in
    the same scope."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.OBSERVATION_CREATE,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    if service_id is not None:
        service = await unit.services.get(
            project.organization_id, project_id, service_id
        )
        if service is None:
            raise NotFoundError("service not found")
    if location_id is not None:
        location = await unit.locations.get(
            project.organization_id, project_id, competitor_id, location_id
        )
        if location is None:
            raise NotFoundError("location not found")
    observation = Observation(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        competitor_id=competitor_id,
        service_id=service_id,
        location_id=location_id,
        kind=kind,
        price_amount=price_amount,
        price_currency=price_currency,
        observed_on=observed_on,
        confidence=MANUAL_CONFIDENCE,
        extraction_version=MANUAL_EXTRACTION_VERSION,
        approval_state=OBSERVATION_PENDING,
        superseded_by=None,
        created_by=principal.app_user_id,
    )
    await unit.observations.create(observation)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="observation.create",
            target_type="observation",
            target_id=str(observation.id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "kind": kind,
            },
        )
    )
    return observation


async def list_observations(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    competitor_id: UUID,
) -> list[Observation]:
    """observation.read — every state, newest first is the repository's
    concern; the review queue endpoint filters pending."""
    project, competitor = await _load_competitor_scope(unit, project_id, competitor_id)
    await authz.require(
        principal,
        Permission.OBSERVATION_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.observations.list_for_competitor(
        project.organization_id, project_id, competitor_id
    )


async def review_queue(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
) -> list[Observation]:
    """The worklist of pending observations awaiting a human decision
    (glossary: Review queue)."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.OBSERVATION_READ,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    return await unit.observations.list_pending_for_project(
        project.organization_id, project_id
    )


async def approve_observation(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    observation_id: UUID,
) -> Observation:
    """observation.review(approve): pending → approved. A different value
    in the same cell supersedes the current approved row and emits
    CompetitorChangeDetected in this transaction; an identical
    re-observation is approved without a Change."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.OBSERVATION_REVIEW,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    observation = await unit.observations.get(
        project.organization_id, project_id, observation_id
    )
    if observation is None:
        raise NotFoundError("observation not found")
    if observation.approval_state != OBSERVATION_PENDING:
        raise ConflictError(
            f"observation is not pending (state: {observation.approval_state})"
        )
    current_approved = await unit.observations.list_approved_for_competitor(
        project.organization_id, project_id, observation.competitor_id, observation.kind
    )
    change_from: Observation | None = None
    for current in current_approved:
        if _same_group(current, observation):
            if _same_value(current, observation):
                continue  # identical re-observation: not a Change
            change_from = current
            break
    await unit.observations.update_state(
        project.organization_id,
        project_id,
        observation_id,
        approval_state=OBSERVATION_APPROVED,
        superseded_by=None,
    )
    if change_from is not None:
        await unit.observations.update_state(
            project.organization_id,
            project_id,
            change_from.id,
            approval_state="superseded",
            superseded_by=observation.id,
        )
        await unit.outbox.add(
            OutboxEvent(
                event_type=COMPETITOR_CHANGE_DETECTED,
                payload={
                    "organization_id": str(project.organization_id),
                    "project_id": str(project_id),
                    "competitor_id": str(observation.competitor_id),
                    "kind": observation.kind,
                    "service_id": (
                        str(observation.service_id) if observation.service_id else None
                    ),
                    "location_id": (
                        str(observation.location_id) if observation.location_id else None
                    ),
                    "previous_observation_id": str(change_from.id),
                    "new_observation_id": str(observation.id),
                    "previous_price_amount": (
                        str(change_from.price_amount)
                        if change_from.price_amount is not None
                        else None
                    ),
                    "new_price_amount": (
                        str(observation.price_amount)
                        if observation.price_amount is not None
                        else None
                    ),
                    "price_currency": observation.price_currency,
                },
            )
        )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="observation.approve",
            target_type="observation",
            target_id=str(observation_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
    return Observation(
        id=observation.id,
        organization_id=observation.organization_id,
        project_id=observation.project_id,
        competitor_id=observation.competitor_id,
        service_id=observation.service_id,
        location_id=observation.location_id,
        kind=observation.kind,
        price_amount=observation.price_amount,
        price_currency=observation.price_currency,
        observed_on=observation.observed_on,
        confidence=observation.confidence,
        extraction_version=observation.extraction_version,
        approval_state=OBSERVATION_APPROVED,
        superseded_by=None,
        created_by=observation.created_by,
    )


async def reject_observation(
    unit: CompetitorUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    observation_id: UUID,
) -> Observation:
    """observation.review(reject): pending → rejected, retained for audit
    (glossary)."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.OBSERVATION_REVIEW,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    observation = await unit.observations.get(
        project.organization_id, project_id, observation_id
    )
    if observation is None:
        raise NotFoundError("observation not found")
    if observation.approval_state != OBSERVATION_PENDING:
        raise ConflictError(
            f"observation is not pending (state: {observation.approval_state})"
        )
    await unit.observations.update_state(
        project.organization_id,
        project_id,
        observation_id,
        approval_state=OBSERVATION_REJECTED,
        superseded_by=None,
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="observation.reject",
            target_type="observation",
            target_id=str(observation_id),
            organization_id=project.organization_id,
            payload={"project_id": str(project_id)},
        )
    )
    return Observation(
        id=observation.id,
        organization_id=observation.organization_id,
        project_id=observation.project_id,
        competitor_id=observation.competitor_id,
        service_id=observation.service_id,
        location_id=observation.location_id,
        kind=observation.kind,
        price_amount=observation.price_amount,
        price_currency=observation.price_currency,
        observed_on=observation.observed_on,
        confidence=observation.confidence,
        extraction_version=observation.extraction_version,
        approval_state=OBSERVATION_REJECTED,
        superseded_by=None,
        created_by=observation.created_by,
    )
