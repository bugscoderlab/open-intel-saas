"""Extraction value types (spec #47).

The result of running an Extractor over one untrusted source text:
a bag of schema-validated items, each carrying its own confidence.
Nothing here is persisted — ticket #50 maps these onto pending
Observations; approval is a separate human gate (#51).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

KIND_SERVICE = "service"
KIND_PRICE = "price"
KIND_PROMOTION = "promotion"
KIND_POSITIONING = "positioning"
KIND_REVIEW_TOPIC = "review_topic"
EXTRACTION_KINDS = (
    KIND_SERVICE,
    KIND_PRICE,
    KIND_PROMOTION,
    KIND_POSITIONING,
    KIND_REVIEW_TOPIC,
)

# Version marker for the extraction prompt+schema contract. Bumping it
# (extract-v2…) marks previously derived observations re-derivable after
# prompt improvements (glossary: Extraction version).
EXTRACTION_VERSION = "extract-v1"

_REVIEW_SENTIMENTS = ("positive", "neutral", "negative")


@dataclass(frozen=True)
class ExtractedItem:
    """One structured claim about the competitor.

    kind: one of EXTRACTION_KINDS. claim: the normalized statement
    (e.g. "Full grooming — RM88"). price_amount/currency: only for
    kind=price. sentiment: only for kind=review_topic. confidence:
    model-reported score in [0, 1]; items outside that range are
    dropped by validation, never silently clamped (spec #49). excerpt:
    the source span supporting the claim, for evidence references.
    """

    kind: str
    claim: str
    confidence: Decimal
    price_amount: Decimal | None = None
    price_currency: str | None = None
    sentiment: str | None = None
    excerpt: str | None = None


@dataclass(frozen=True)
class ExtractionResult:
    items: tuple[ExtractedItem, ...] = field(default_factory=tuple)

    def of_kind(self, kind: str) -> tuple[ExtractedItem, ...]:
        return tuple(item for item in self.items if item.kind == kind)

RUN_PENDING = "pending"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_STATES = (RUN_PENDING, RUN_SUCCEEDED, RUN_FAILED)


@dataclass(frozen=True)
class ExtractionRun:
    """One extraction attempt over one collection snapshot (ticket #50).

    Enqueued through the outbox (ADR-004) and drained off-request; the
    partial unique index on (project, snapshot, version) makes a
    pending/succeeded run idempotent at request time, and a failed run
    can be re-enqueued for retry."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    snapshot_id: UUID
    status: str
    extraction_version: str
    error: str | None
    requested_by: UUID
