"""In-process poll loops for collection (tickets #42/#44).

Two ADR-004 loops, both wired in the composition root (serve.py):
  * the run dispatcher drains pending job_runs off-request — the API
    only enqueues (request/claim + outbox event in one transaction);
  * the scheduler claims due schedules (job_run + CollectionDue outbox
    event + next_due_at advance in one transaction), then drains.

Tests call ``drain_pending_runs`` / ``run_scheduler_tick`` directly for
determinism; ``no_competing_dispatcher`` in conftest keeps a dev API
(port 5055) from racing the test suite over the same queues.
"""

import asyncio
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.collection.application.services.collect_service import (
    drain_pending_runs,
)
from modules.collection.application.services.job_service import claim_due_jobs
from modules.collection.domain.ports import WebsiteFetcher
from modules.collection.infrastructure.unit_of_work import SqlCollectionUnit

POLL_INTERVAL_SECONDS = 2.0


async def run_collection_dispatcher(
    engine: AsyncEngine, fetcher: WebsiteFetcher
) -> None:
    """Poll for pending runs until cancelled; one drain tick is one
    transaction and failure-isolated per run (see drain_pending_runs)."""
    while True:
        try:
            processed = await drain_pending_runs(
                lambda: SqlCollectionUnit(engine), fetcher
            )
            if processed:
                logger.info("collection: drained {} run(s)", processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the loop must never die
            logger.exception("collection dispatcher tick failed: {}", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def run_scheduler_tick(unit_factory, *, now: datetime | None = None) -> int:
    """Claim due schedules in ONE transaction (run row + outbox event +
    next_due_at advance), so a due job is never claimed twice. Tests
    call this directly; the production loop below repeats it."""
    unit = unit_factory()
    async with unit:
        claimed = await claim_due_jobs(unit, now or datetime.now(UTC))
        await unit.commit()
        return claimed


async def run_collection_scheduler(engine: AsyncEngine, fetcher: WebsiteFetcher) -> None:
    """Poll for due schedules until cancelled: claim, then drain the
    freshly claimed runs through the same pipeline as on-demand work.
    A failing job's run is recorded and the schedule backs off — the
    queue is never stalled (spec #41 user stories 9/10)."""
    while True:
        try:
            claimed = await run_scheduler_tick(lambda: SqlCollectionUnit(engine))
            if claimed:
                logger.info("collection: claimed {} due job(s)", claimed)
                await drain_pending_runs(lambda: SqlCollectionUnit(engine), fetcher)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the loop must never die
            logger.exception("collection scheduler tick failed: {}", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
