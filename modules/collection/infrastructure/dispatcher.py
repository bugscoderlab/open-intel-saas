"""In-process poll loop for pending collection jobs (ticket #42).

Mirrors the research dispatcher (ADR-004): the API only enqueues
(request_collection + outbox event in one transaction); this loop runs
the fetches off-request. Single-process by design — the Celery/Redis
move is a deliberate later decision (ADR-004) and gets its own PDR.

Tests call ``drain_pending_jobs`` directly for determinism instead of
this loop; ``no_competing_dispatcher`` in conftest additionally keeps a
dev API (port 5055) from racing the test suite over the same job queue.
"""

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.collection.application.services.collect_service import drain_pending_jobs
from modules.collection.domain.ports import WebsiteFetcher
from modules.collection.infrastructure.unit_of_work import SqlCollectionUnit

POLL_INTERVAL_SECONDS = 2.0


async def run_collection_dispatcher(
    engine: AsyncEngine, fetcher: WebsiteFetcher
) -> None:
    """Poll for pending jobs until cancelled; one drain tick is one
    transaction and failure-isolated per job (see drain_pending_jobs)."""
    while True:
        try:
            processed = await drain_pending_jobs(
                lambda: SqlCollectionUnit(engine), fetcher
            )
            if processed:
                logger.info("collection: drained {} job(s)", processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the loop must never die
            logger.exception("collection dispatcher tick failed: {}", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
