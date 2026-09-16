"""Intelligence-chat domain: tool value types, the router port, typed
errors. Pure domain — no framework or provider imports
(lint-imports contract; spec #58).
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

MAX_INVOCATIONS_PER_ANSWER = 5


@dataclass(frozen=True)
class Citation:
    """A structured reference to a tool result (glossary: Citation).
    origin names the tool; ref carries the tool-specific identifiers
    (source id + excerpt span, observation id, competitor id…)."""

    origin: str
    ref: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of one tool invocation. Tool-level failures are
    OUTCOMES, never exceptions — the orchestration notes them and the
    answer continues (spec exit condition)."""

    tool: str
    ok: bool
    payload: dict[str, Any] | None = None
    error: str | None = None
    citations: tuple[Citation, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UnavailableNote:
    """Why a planned tool could not contribute to this answer."""

    tool: str
    reason: str


@dataclass(frozen=True)
class ToolSpec:
    """The declared contract of one chat tool (glossary: Chat tool)."""

    name: str
    description: str
    arguments_schema: dict[str, Any]  # JSON Schema (draft 2020-12 subset)
    required_permission: str
    invocation_cap: int = 3


@dataclass(frozen=True)
class ToolContext:
    """Out-of-band scope handed to handlers — never part of the
    validated arguments (schemas are additionalProperties: false)."""

    project_id: UUID


@dataclass(frozen=True)
class PlanStep:
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolPlan:
    steps: tuple[PlanStep, ...]


@dataclass(frozen=True)
class ResearchHit:
    """One research-search result as the chatbot sees it (bounded,
    citation-ready — the shell renders, the tool never invents refs)."""

    source_id: UUID
    title: str
    excerpt: str
    score: float


@dataclass(frozen=True)
class ServicePrice:
    service_id: UUID
    service_name: str
    latest_price_amount: str | None
    latest_price_currency: str | None


@dataclass(frozen=True)
class CompetitorProfile:
    """The competitor_lookup answer: identity + locations + services
    with their latest approved prices."""

    competitor_id: UUID
    name: str
    locations: tuple[str, ...]
    services: tuple[ServicePrice, ...]


@dataclass(frozen=True)
class MetricRun:
    """An analytics-metric result, serialized for the composer."""

    metric: str
    unit: str
    description: str
    points: tuple[dict, ...]
    truncated: bool


__all__ = [
    "CompetitorProfile",
    "Citation",
    "MetricRun",
    "ResearchHit",
    "ServicePrice",
    "MAX_INVOCATIONS_PER_ANSWER",
    "PlanStep",
    "ToolContext",
    "ToolPlan",
    "ToolResult",
    "ToolSpec",
    "UnavailableNote",
]
