"""Test-side implementations of the extraction ports (ticket #50).

Same shapes as the serve.py composition-root wiring, built over the
test engine: the snapshot source reads collection.snapshots and the
observation sink writes pending observations + snapshot evidence links
through the competitor-intelligence unit. Keeping them here (not in
fakes.py) because they are real-DB adapters, not fakes.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.collection.infrastructure.db import snapshots as snapshots_table
from modules.collection.infrastructure.unit_of_work import SqlCollectionUnit
from modules.competitor_intelligence.application.services.observation_service import (
    record_proposed_observations,
)
from modules.competitor_intelligence.domain.entities import ProposedObservation
from modules.competitor_intelligence.infrastructure.unit_of_work import (
    SqlCompetitorUnit,
)
from modules.extraction.domain.ports import (
    ProposedFact,
    SnapshotContent,
)


class TestSnapshotSource:
    async def get(self, snapshot_id) -> SnapshotContent | None:
        async with SqlCollectionUnit(self._engine) as unit:
            assert unit._session is not None
            result = await unit._session.execute(  # noqa: SLF001
                select(snapshots_table).where(snapshots_table.c.id == snapshot_id)
            )
            row = result.first()
            if row is None:
                return None
            return SnapshotContent(
                snapshot_id=row.id,
                project_id=row.project_id,
                competitor_id=row.competitor_id,
                url=row.url,
                raw_payload=row.raw_payload,
                captured_at=row.captured_at,
            )

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine


class TestObservationSink:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record_proposed(
        self,
        *,
        organization_id,
        project_id,
        competitor_id,
        snapshot_id,
        observed_on,
        extraction_version,
        facts: list[ProposedFact],
        recorded_by,
    ) -> int:
        async with SqlCompetitorUnit(self._engine) as unit:
            created = await record_proposed_observations(
                unit,
                project_id=project_id,
                competitor_id=competitor_id,
                snapshot_id=snapshot_id,
                observed_on=observed_on,
                extraction_version=extraction_version,
                proposed=[
                    ProposedObservation(
                        kind=fact.kind,
                        confidence=fact.confidence,
                        price_amount=fact.price_amount,
                        price_currency=fact.price_currency,
                        excerpt=fact.excerpt,
                    )
                    for fact in facts
                ],
                recorded_by=recorded_by,
            )
            await unit.commit()
            return len(created)
