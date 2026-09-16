"""Plan validation for router output (ticket #60): the router's JSON
must parse to the ToolPlan shape with steps drawn from the allowlist
and arguments that validate. Anything else is a PlanValidationError —
the adapter retries once with a repair hint, then drops to an empty
plan (the orchestration reports unavailable analysis)."""

import json

from modules.intelligence_chat.application.tools import ChatTool, ToolRegistry
from modules.intelligence_chat.domain.entities import PlanStep, ToolPlan, ToolSpec
from modules.intelligence_chat.domain.errors import PlanValidationError


def parse_plan_payload(text: str) -> ToolPlan:
    """Strict parse: single JSON object, no fences, no prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        raise PlanValidationError("plan must be bare JSON, not fenced")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"plan is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanValidationError("plan must be a JSON object")
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        raise PlanValidationError("plan must contain a 'steps' array")
    steps: list[PlanStep] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            raise PlanValidationError("each step must be an object")
        tool = raw.get("tool")
        arguments = raw.get("arguments", {})
        if not isinstance(tool, str) or not isinstance(arguments, dict):
            raise PlanValidationError(
                "step needs string 'tool' and object 'arguments'"
            )
        steps.append(PlanStep(tool=tool, arguments=arguments))
    return ToolPlan(steps=tuple(steps))


def validate_plan_against_allowlist(
    plan: ToolPlan, allowlist: tuple[ToolSpec, ...]
) -> ToolPlan:
    """Every step must name an allowed tool with valid arguments."""
    allowed = {spec.name: spec for spec in allowlist}
    registry = ToolRegistry()

    async def _placeholder(arguments: dict):  # pragma: no cover
        raise NotImplementedError

    for spec in allowlist:
        registry.register(ChatTool(spec=spec, handler=_placeholder))
    validated: list[PlanStep] = []
    for step in plan.steps:
        if step.tool not in allowed:
            raise PlanValidationError(
                f"tool {step.tool!r} is not in the allowlist"
            )
        registry.validate_arguments(step)
        validated.append(step)
    return ToolPlan(steps=tuple(validated))
