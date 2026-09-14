"""Competitor-intelligence domain entities (spec #31) — pure dataclasses
(plan §14.2). Tenant-owned rows carry organization_id + project_id like
every other module's rows; Competitor belongs to a Project (a Market when
the project is configured for competitor intelligence — the same
real-world business is a separate record per market, deliberately).
"""

from dataclasses import dataclass
from uuid import UUID


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
