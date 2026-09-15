"""Extraction use cases (ticket #50, spec #47): enqueue an extraction
run over one snapshot (editor+, matrix-gated, audited, idempotent) and
drain pending runs off-request (ADR-004) through the Extractor port,
recording proposed observations via the ObservationSink port.

The drain is failure-isolated per run: a missing snapshot, a provider
failure, or a validation failure marks THAT run failed with the typed
error and an audit row — the queue is never stalled and snapshots are
never touched (the exit condition of spec #41 carries over).
"""

from uuid import UUID, uuid4

from modules.extraction.domain.entities import (
    EXTRACTION_VERSION,
    RUN_FAILED,
    RUN_PENDING,
    RUN_SUCCEEDED,
    ExtractionRun,
)
from modules.extraction.domain.errors import ExtractionError
from modules.extraction.domain.events import EXTRACTION_REQUESTED
from modules.extraction.domain.ports import (
    Extractor,
    ObservationSink,
    ProposedFact,
    SnapshotSource,
)
from modules.extraction.domain.unit_of_work import ExtractionUnit
from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import AuditEntry, OutboxEvent
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def request_extraction(
    unit: ExtractionUnit,
    authz: AuthorizationService,
    principal: Principal,
    snapshot_source: SnapshotSource,
    *,
    project_id: UUID,
    competitor_id: UUID,
    snapshot_id: UUID,
) -> ExtractionRun:
    """extraction.run — enqueue one extraction attempt over a snapshot.

    Idempotent per (snapshot, extraction_version): an existing
    pending or succeeded run is returned as-is; only a FAILED run may
    be re-enqueued (retry after a visible failure)."""
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    await authz.require(
        principal,
        Permission.EXTRACTION_RUN,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    content = await snapshot_source.get(snapshot_id)
    if (
        content is None
        or content.project_id != project_id
        or content.competitor_id != competitor_id
    ):
        raise NotFoundError("snapshot not found")

    existing = await unit.extraction_runs.find_for_snapshot(
        project.organization_id,
        project_id,
        snapshot_id,
        EXTRACTION_VERSION,
    )
    if existing is not None and existing.status in (RUN_PENDING, RUN_SUCCEEDED):
        return existing

    run = ExtractionRun(
        id=uuid4(),
        organization_id=project.organization_id,
        project_id=project_id,
        competitor_id=competitor_id,
        snapshot_id=snapshot_id,
        status=RUN_PENDING,
        extraction_version=EXTRACTION_VERSION,
        error=None,
        requested_by=principal.app_user_id,
    )
    await unit.extraction_runs.create(run)
    await unit.outbox.add(
        OutboxEvent(
            event_type=EXTRACTION_REQUESTED,
            payload={
                "organization_id": str(project.organization_id),
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "snapshot_id": str(snapshot_id),
                "extraction_run_id": str(run.id),
            },
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="extraction.request",
            target_type="collection_snapshot",
            target_id=str(snapshot_id),
            organization_id=project.organization_id,
            payload={
                "project_id": str(project_id),
                "competitor_id": str(competitor_id),
                "extraction_version": EXTRACTION_VERSION,
            },
        )
    )
    return run


async def _process_run(
    unit: ExtractionUnit,
    extractor: Extractor,
    snapshot_source: SnapshotSource,
    sink: ObservationSink,
    run: ExtractionRun,
) -> None:
    try:
        content = await snapshot_source.get(run.snapshot_id)
        if content is None:
            raise ExtractionError("snapshot is no longer available")
        result = await extractor.extract(
            source_text=content.raw_payload, source_url=content.url
        )
        facts = [
            ProposedFact(
                kind=item.kind,
                confidence=item.confidence,
                price_amount=item.price_amount,
                price_currency=item.price_currency,
                excerpt=item.excerpt,
                claim=item.claim,
                sentiment=item.sentiment,
            )
            for item in result.items
        ]
        await sink.record_proposed(
            organization_id=run.organization_id,
            project_id=run.project_id,
            competitor_id=run.competitor_id,
            snapshot_id=run.snapshot_id,
            observed_on=content.captured_at.date(),
            extraction_version=run.extraction_version,
            facts=facts,
            recorded_by=run.requested_by,
        )
        await unit.extraction_runs.mark_result(
            run.organization_id,
            run.project_id,
            run.id,
            status=RUN_SUCCEEDED,
            error=None,
        )
        await unit.audit.record(
            AuditEntry(
                actor_id=run.requested_by,
                action="extraction.succeeded",
                target_type="collection_snapshot",
                target_id=str(run.snapshot_id),
                organization_id=run.organization_id,
                payload={
                    "project_id": str(run.project_id),
                    "extraction_run_id": str(run.id),
                    "observations_proposed": len(facts),
                },
            )
        )
    except Exception as exc:  # noqa: BLE001 — one bad run must never
        # stall the drain or roll back other runs' work (ADR-004).
        await unit.extraction_runs.mark_result(
            run.organization_id,
            run.project_id,
            run.id,
            status=RUN_FAILED,
            error=str(exc),
        )
        await unit.audit.record(
            AuditEntry(
                actor_id=run.requested_by,
                action="extraction.failed",
                target_type="extraction_run",
                target_id=str(run.id),
                organization_id=run.organization_id,
                payload={
                    "project_id": str(run.project_id),
                    "snapshot_id": str(run.snapshot_id),
                    "error": str(exc),
                },
            )
        )


async def drain_pending_extractions(
    unit_factory,
    extractor: Extractor,
    snapshot_source: SnapshotSource,
    sink: ObservationSink,
    *,
    limit: int = 100,
) -> int:
    """Drain pending extraction runs in ONE transaction, off-request
    (ADR-004). Each run is failure-isolated inside the drain (see
    _process_run). Tests call this directly for determinism; the
    production poll loop lives in infrastructure/dispatcher.py."""
    unit = unit_factory()
    async with unit:
        runs = await unit.extraction_runs.list_pending(limit=limit)
        for run in runs:
            await _process_run(unit, extractor, snapshot_source, sink, run)
        await unit.commit()
        return len(runs)
