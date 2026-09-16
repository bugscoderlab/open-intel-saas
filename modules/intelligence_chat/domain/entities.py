"""Intelligence-chat domain: tool value types, the router port, typed
errors. Pure domain — no framework or provider imports
(lint-imports contract; spec #58).
"""

from dataclasses import dataclass, field
from typing import Any

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
class PlanStep:
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolPlan:
    steps: tuple[PlanStep, ...]


__all__ = [
    "Citation",
    "MAX_INVOCATIONS_PER_ANSWER",
    "PlanStep",
    "ToolPlan",
    "ToolResult",
    "ToolSpec",
    "UnavailableNote",
]
