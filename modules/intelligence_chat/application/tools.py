"""Tool framework (ticket #60, spec #58): registry, strict argument
validation, permission-derived allowlists, and the per-request budget.

Design decisions recorded on the ticket:
* Argument schemas are JSON Schema (draft 2020-12 subset) validated
  with the ``jsonschema`` package — total validation: unknown
  properties, wrong types, and missing required arguments all reject
  before the handler runs.
* Tool-level failures (validation, permission, cap, handler error) are
  OUTCOMES (ToolResult ok=False / UnavailableNote), never exceptions —
  the answer continues without that tool (spec exit condition).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import jsonschema

from modules.intelligence_chat.domain.entities import (
    MAX_INVOCATIONS_PER_ANSWER,
    PlanStep,
    ToolContext,
    ToolResult,
    ToolSpec,
)
from modules.intelligence_chat.domain.errors import (
    PlanValidationError,
    ToolArgumentError,
)

HandlerFn = Callable[[dict, ToolContext], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ChatTool:
    """A registered tool: its declared spec plus its handler."""

    spec: ToolSpec
    handler: HandlerFn


@dataclass
class Budget:
    """Per-request invocation budget (spec assumption 4)."""

    remaining: int = MAX_INVOCATIONS_PER_ANSWER
    per_tool_spent: dict[str, int] = field(default_factory=dict)


class ToolRegistry:
    """Registry + execution guard. The registry owns no state beyond
    the registered tools; budgets are per-answer."""

    def __init__(self, tools: tuple[ChatTool, ...] = ()) -> None:
        self._tools: dict[str, ChatTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ChatTool) -> None:
        if tool.spec.name in self._tools:
            raise ValueError(f"duplicate tool {tool.spec.name!r}")
        self._tools[tool.spec.name] = tool

    def allowlist_for(self, permissions: frozenset[str]) -> tuple[ToolSpec, ...]:
        """The router's allowlist: only tools the caller may run."""
        return tuple(
            tool.spec
            for tool in self._tools.values()
            if tool.spec.required_permission in permissions
        )

    def validate_arguments(self, step: PlanStep) -> None:
        """Total JSON-Schema validation of one plan step's arguments."""
        tool = self._tools.get(step.tool)
        if tool is None:
            raise PlanValidationError(f"unknown tool {step.tool!r}")
        try:
            jsonschema.validate(
                step.arguments,
                tool.spec.arguments_schema,
                format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
            )
        except jsonschema.ValidationError as exc:
            raise ToolArgumentError(
                f"invalid arguments for {step.tool!r}: {exc.message}"
            ) from exc

    async def execute(
        self,
        step: PlanStep,
        *,
        context: ToolContext,
        permissions: frozenset[str],
        budget: Budget,
    ) -> ToolResult:
        """Execute one planned step under permission + budget guards.
        Every guard failure is a typed outcome, never an exception."""
        tool = self._tools.get(step.tool)
        if tool is None:
            return ToolResult(tool=step.tool, ok=False, error="unknown tool")
        if tool.spec.required_permission not in permissions:
            return ToolResult(
                tool=step.tool, ok=False, error="missing permission"
            )
        if budget.remaining <= 0:
            return ToolResult(
                tool=step.tool, ok=False, error="invocation budget spent"
            )
        spent = budget.per_tool_spent.get(step.tool, 0)
        if spent >= tool.spec.invocation_cap:
            return ToolResult(
                tool=step.tool, ok=False, error="tool invocation cap spent"
            )
        try:
            self.validate_arguments(step)
        except (PlanValidationError, ToolArgumentError) as exc:
            return ToolResult(tool=step.tool, ok=False, error=str(exc))
        budget.remaining -= 1
        budget.per_tool_spent[step.tool] = spent + 1
        try:
            return await tool.handler(step.arguments, context)
        except Exception as exc:  # noqa: BLE001 — a broken tool must not
            # break the answer; it becomes an unavailable note.
            return ToolResult(tool=step.tool, ok=False, error=str(exc))
