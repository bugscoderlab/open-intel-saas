"""Competitor-intelligence domain entities (spec #31) — pure dataclasses
(plan §14.2). Tenant-owned rows carry organization_id + project_id like
every other module's rows; Competitor belongs to a Project (a Market when
the project is configured for competitor intelligence — the same
real-world business is a separate record per market, deliberately).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

# Observation lifecycle (ticket #34). Manual entries land "pending" and
# reach "approved"/"rejected" through the review queue; "superseded" is
# the mechanical marker of a Change (glossary): a newer approved
# observation took over the same (competitor, service, location, kind).
OBSERVATION_PENDING = "pending"
OBSERVATION_APPROVED = "approved"
OBSERVATION_REJECTED = "rejected"
OBSERVATION_SUPERSEDED = "superseded"
OBSERVATION_STATES = (
    OBSERVATION_PENDING,
    OBSERVATION_APPROVED,
    OBSERVATION_REJECTED,
    OBSERVATION_SUPERSEDED,
)
KIND_PRICE = "price"
# Manual observations: human-verified, so full confidence; the version
# marker keeps the extraction-version contract populated from day one
# (spec #31 assumption 3).
MANUAL_CONFIDENCE = Decimal("1.0")
MANUAL_EXTRACTION_VERSION = "manual-v1"


@dataclass(frozen=True)
class Competitor:
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    website: str | None
    notes: str | None
    created_by: UUID


@dataclass(frozen=True)
class Location:
    """A physical branch where a Competitor operates (glossary)."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    name: str
    address: str | None
    created_by: UUID


@dataclass(frozen=True)
class Service:
    """A canonical offering in a Market's service catalog (glossary):
    defined once per Project so price comparisons are apples-to-apples."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    created_by: UUID


@dataclass(frozen=True)
class Observation:
    """A single stored, approvable fact about a competitor (glossary).
    Rows are never updated in place except the approval-state flip —
    a new approved value for the same (competitor, service, location,
    kind) supersedes the old row rather than overwriting it."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    service_id: UUID | None
    location_id: UUID | None
    kind: str
    price_amount: Decimal | None
    price_currency: str | None
    observed_on: date
    confidence: Decimal
    extraction_version: str
    approval_state: str
    superseded_by: UUID | None
    created_by: UUID


# Evidence targets (ticket #35): the kinds of research rows a link may
# point at. Target IDs stay opaque UUIDs — no cross-module FK or import
# (plan §14.4 rule 2; existence validation deferred to Phase 5).
EVIDENCE_TARGET_SOURCE = "source"
EVIDENCE_TARGET_NOTEBOOK = "notebook"
# Phase 5 (ticket #50): extraction attaches evidence to collection
# snapshots — the snapshot id stays opaque (no cross-module FK).
EVIDENCE_TARGET_SNAPSHOT = "snapshot"
EVIDENCE_TARGET_KINDS = (
    EVIDENCE_TARGET_SOURCE,
    EVIDENCE_TARGET_NOTEBOOK,
    EVIDENCE_TARGET_SNAPSHOT,
)


@dataclass(frozen=True)
class ProposedObservation:
    """One machine-proposed fact from extraction (ticket #50) — the
    input shape for recording pending observations. Unlike manual
    entries the confidence comes from the extractor and the kind may be
    promotion/positioning/review_topic/service, not only price."""

    kind: str
    confidence: Decimal
    price_amount: Decimal | None = None
    price_currency: str | None = None
    excerpt: str | None = None


@dataclass(frozen=True)
class EvidenceLink:
    """Connects a Competitor (and optionally one of its Observations) to
    a research Source or Notebook, with an excerpt pointing at the exact
    span. Manual attaches are approved immediately; the state column is
    retained for Phase 5 automation (glossary: Evidence)."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    observation_id: UUID | None
    target_kind: str
    target_id: UUID
    excerpt: str | None
    excerpt_start: int | None
    excerpt_end: int | None
    approval_state: str
    created_by: UUID
