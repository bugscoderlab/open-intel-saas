"""The extraction unit of work: platform repositories plus extraction
runs, in one transaction. Extraction requires Platform only — snapshot
content arrives through the SnapshotSource port and observation writes
through the ObservationSink port, both wired by the composition root
(module independence, plan §14.4)."""

from typing import Protocol
from uuid import UUID

from modules.extraction.domain.entities import ExtractionRun
from modules.platform.domain.unit_of_work import PlatformUnit


class ExtractionRuns(Protocol):
    """Extraction attempt repository — one row per (snapshot, version)
    attempt; the partial unique index backs request-level idempotency."""

    async def create(self, run: ExtractionRun) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, run_id: UUID
    ) -> ExtractionRun | None: ...
    async def list_pending(self, *, limit: int = 100) -> list[ExtractionRun]: ...
    async def mark_result(
        self,
        organization_id: UUID,
        project_id: UUID,
        run_id: UUID,
        *,
        status: str,
        error: str | None,
    ) -> None: ...
    async def find_for_snapshot(
        self,
        organization_id: UUID,
        project_id: UUID,
        snapshot_id: UUID,
        extraction_version: str,
    ) -> ExtractionRun | None: ...


class ExtractionUnit(PlatformUnit, Protocol):
    """One transaction worth of repositories: the platform's plus
    extraction runs."""

    extraction_runs: ExtractionRuns
