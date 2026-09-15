"""Analytics domain: metric value types, the approved-facts port, typed
errors. Pure domain — no framework or cross-module imports
(lint-imports contract; spec #52 assumption 2).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar
from uuid import UUID

from modules.analytics.domain.errors import AnalyticsQueryError

T = TypeVar("T")

DEFAULT_ROW_CAP = 10_000
STATEMENT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Page(Generic[T]):
    """One guarded query result: the rows plus the guardrail flag.

    The row cap never fails a query — it truncates and says so, so
    dashboards degrade to partial data instead of erroring (spec #52
    assumption 5)."""

    rows: tuple[T, ...]
    truncated: bool = False


@dataclass(frozen=True)
class ApprovedObservation:
    """Read view of one approved, non-superseded observation — the only
    durable truth analytics consumes (glossary: Observation)."""

    id: UUID
    competitor_id: UUID
    service_id: UUID | None
    location_id: UUID | None
    kind: str
    price_amount: Decimal | None
    price_currency: str | None
    observed_on: date
    superseded_by: UUID | None
    created_at: datetime
    claim: str | None = None
    sentiment: str | None = None


@dataclass(frozen=True)
class CompetitorSummary:
    """Read view of a competitor for analytics joins (names only)."""

    id: UUID
    project_id: UUID
    name: str


@dataclass(frozen=True)
class CatalogService:
    id: UUID
    project_id: UUID
    name: str


@dataclass(frozen=True)
class CompetitorLocation:
    id: UUID
    project_id: UUID
    competitor_id: UUID
    name: str


@dataclass(frozen=True)
class MetricResult:
    """The outcome of running one named metric."""

    metric: str
    unit: str
    description: str
    points: tuple[dict, ...]
    truncated: bool = False


__all__ = [
    "AnalyticsQueryError",
    "ApprovedObservation",
    "CatalogService",
    "CompetitorSummary",
    "CompetitorLocation",
    "DEFAULT_ROW_CAP",
    "MetricResult",
    "Page",
    "STATEMENT_TIMEOUT_SECONDS",
]
