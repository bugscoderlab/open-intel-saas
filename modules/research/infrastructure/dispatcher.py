"""In-process async dispatcher over outbox_events (ticket #23, ADR-004).

The API never processes sources in-request: it writes the source row and
a SourceSubmitted outbox event in one transaction (plan §14.5), returns
202, and this dispatcher does the extraction→chunking work off-request.
Single-process by design — the Celery/Redis move is a deliberate later
decision (ADR-004) and gets its own PDR when taken.

Per event, the pipeline and the event's ``published_at`` mark commit in
one transaction; a failing pipeline rolls back and records the failure
(status failed + SourceProcessingCompleted event) in a fresh transaction,
so a poison event can never stall the queue. Tests call
``drain_pending_sources`` directly for determinism; ``run_dispatcher`` is
the production poll loop, wired in the composition root (serve.py).
"""

import asyncio
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.platform.application.errors import NotFoundError
from modules.platform.domain.storage import FileStorage
from modules.research.application.processing import (
    fail_text_source,
    process_source,
)
from modules.research.domain.embedder import Embedder
from modules.research.domain.events import SOURCE_SUBMITTED
from modules.research.infrastructure.unit_of_work import SqlResearchUnit


async def _claim_events(
    engine: AsyncEngine, *, limit: int
) -> list[tuple[UUID, dict]]:
    async with SqlResearchUnit(engine) as unit:
        records = await unit.outbox.list_unpublished(SOURCE_SUBMITTED, limit=limit)
        return [(record.id, record.payload) for record in records]


async def _record_failure(
    engine: AsyncEngine,
    *,
    event_id: UUID,
    payload: dict,
    error: str,
) -> None:
    """Failure recording in ONE transaction: source flips to failed with
    the error message, a SourceProcessingCompleted event goes out, and
    the poison event is marked published so the queue drains. A source
    deleted mid-flight has no row to flip — the event is still marked
    published."""
    organization_id = UUID(payload["organization_id"])
    project_id = UUID(payload["project_id"])
    source_id = UUID(payload["source_id"])
    try:
        async with SqlResearchUnit(engine) as unit:
            await fail_text_source(
                unit,
                organization_id=organization_id,
                project_id=project_id,
                source_id=source_id,
                error=error,
            )
            await unit.outbox.mark_published(event_id)
            await unit.commit()
    except NotFoundError:
        logger.warning(
            "source {} gone before failure could be recorded", payload["source_id"]
        )
        async with SqlResearchUnit(engine) as unit:
            await unit.outbox.mark_published(event_id)
            await unit.commit()


async def drain_pending_sources(
    engine: AsyncEngine,
    *,
    embedder: Embedder,
    storage: FileStorage | None = None,
    limit: int = 25,
) -> int:
    """Process up to ``limit`` unpublished SourceSubmitted events with the
    given embedder (the composition seam: Esperanto in serve.py, a
    deterministic fake in tests — no real provider APIs).

    ``storage`` is the FileStorage port (ticket #29): required for file
    sources; absent, a file source lands failed/retryable with a typed
    "not configured" error instead of blocking the queue. Returns the
    number of events consumed (succeeded or recorded-failed)."""
    events = await _claim_events(engine, limit=limit)
    for event_id, payload in events:
        organization_id = UUID(payload["organization_id"])
        project_id = UUID(payload["project_id"])
        source_id = UUID(payload["source_id"])
        try:
            async with SqlResearchUnit(engine) as unit:
                await process_source(
                    unit,
                    organization_id=organization_id,
                    project_id=project_id,
                    source_id=source_id,
                    embedder=embedder,
                    storage=storage,
                )
                await unit.outbox.mark_published(event_id)
                await unit.commit()
        except Exception as exc:  # noqa: BLE001 — poison events must not stall the queue
            logger.exception("processing source {} failed", source_id)
            await _record_failure(
                engine, event_id=event_id, payload=payload, error=str(exc)
            )
    return len(events)


async def run_dispatcher(
    engine: AsyncEngine,
    *,
    embedder: Embedder,
    storage: FileStorage | None = None,
    poll_interval_seconds: float = 2.0,
    batch_size: int = 25,
) -> None:
    """The production loop: drain, sleep, repeat. Runs until cancelled."""
    while True:
        try:
            await drain_pending_sources(
                engine, embedder=embedder, storage=storage, limit=batch_size
            )
        except Exception:  # noqa: BLE001 — the loop must outlive a bad iteration
            logger.exception("research dispatcher iteration failed")
        await asyncio.sleep(poll_interval_seconds)
