"""In-process poll loop for extraction (ticket #50, ADR-004).

POST /extract only enqueues (run row + outbox event in one transaction);
this loop drains pending runs off-request through the Extractor port
and records proposed observations via the sink. Mirrors the collection
dispatcher exactly — tests drive ``drain_pending_extractions`` directly
for determinism.
"""

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.extraction.application.services.extract_service import (
    drain_pending_extractions,
)
from modules.extraction.domain.ports import (
    Extractor,
    ObservationSink,
    SnapshotSource,
)
from modules.extraction.infrastructure.unit_of_work import SqlExtractionUnit

POLL_INTERVAL_SECONDS = 2.0


async def run_extraction_dispatcher(
    engine: AsyncEngine,
    extractor: Extractor,
    snapshot_source: SnapshotSource,
    sink: ObservationSink,
) -> None:
    """Poll for pending extraction runs until cancelled; one drain tick
    is one transaction and failure-isolated per run."""
    while True:
        try:
            processed = await drain_pending_extractions(
                lambda: SqlExtractionUnit(engine),
                extractor,
                snapshot_source,
                sink,
            )
            if processed:
                logger.info("extraction: drained {} run(s)", processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the loop must never die
            logger.exception("extraction dispatcher tick failed: {}", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
