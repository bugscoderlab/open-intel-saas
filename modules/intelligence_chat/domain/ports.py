"""Domain ports for intelligence chat (spec #58)."""

from typing import Protocol, runtime_checkable

from modules.intelligence_chat.domain.entities import ToolPlan, ToolSpec


@runtime_checkable
class ToolRouter(Protocol):
    """Decides which tools a question needs. Implementations must plan
    ONLY from the provided allowlist — the framework validates anyway,
    but adapters are expected to respect it natively."""

    async def plan(
        self, *, question: str, allowlist: tuple[ToolSpec, ...]
    ) -> ToolPlan: ...
