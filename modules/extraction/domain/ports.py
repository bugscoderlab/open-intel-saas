"""Domain ports for extraction (spec #49)."""

from typing import Protocol, runtime_checkable

from modules.extraction.domain.entities import ExtractionResult


@runtime_checkable
class Extractor(Protocol):
    """Turns one untrusted source text into a validated structured
    result. Implementations: infrastructure LLM adapter (reference),
    fakes in tests. Raises typed Extraction* errors only."""

    async def extract(
        self, *, source_text: str, source_url: str | None = None
    ) -> ExtractionResult: ...


from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class SnapshotContent:
    """What the extraction drain needs from a collection snapshot. The
    id/competitor/project stay explicit so the drain can verify scope;
    the snapshot id remains an opaque reference (no cross-module FK)."""

    snapshot_id: UUID
    project_id: UUID
    competitor_id: UUID
    url: str
    raw_payload: str
    captured_at: datetime


@dataclass(frozen=True)
class ProposedFact:
    """One validated extraction item, mapped to a pending Observation by
    the sink. claim text itself is not stored on observations — the
    excerpt carries the evidence span."""

    kind: str
    confidence: Decimal
    price_amount: Decimal | None = None
    price_currency: str | None = None
    excerpt: str | None = None


@runtime_checkable
class SnapshotSource(Protocol):
    """Supplies snapshot content by id. Implemented by the composition
    root over the collection repositories (module independence: the
    extraction module never imports collection)."""

    async def get(self, snapshot_id: UUID) -> SnapshotContent | None: ...


@runtime_checkable
class ObservationSink(Protocol):
    """Persists proposed facts as pending observations plus snapshot
    evidence links. Implemented by the composition root over the
    competitor-intelligence unit of work."""

    async def record_proposed(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        competitor_id: UUID,
        snapshot_id: UUID,
        observed_on: date,
        extraction_version: str,
        facts: list[ProposedFact],
        recorded_by: UUID,
    ) -> int: ...
