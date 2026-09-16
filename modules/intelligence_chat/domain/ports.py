"""Domain ports for intelligence chat (spec #58).

The data tools never import another business module: the composition
root implements these ports over the research/competitor/analytics
services, and tests use scripted fakes. Authorization for all three is
the tool's required_permission, checked by the registry BEFORE the
handler runs — so the port layer deliberately carries no authz (a
double gate would be a second matrix to maintain)."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from modules.intelligence_chat.domain.entities import (
    CompetitorProfile,
    MetricRun,
    ResearchHit,
    ToolPlan,
    ToolSpec,
)


@runtime_checkable
class ToolRouter(Protocol):
    """Decides which tools a question needs. Implementations must plan
    ONLY from the provided allowlist — the framework validates anyway,
    but adapters are expected to respect it natively."""

    async def plan(
        self, *, question: str, allowlist: tuple[ToolSpec, ...]
    ) -> ToolPlan: ...


@runtime_checkable
class ResearchSearchPort(Protocol):
    """Top-k keyword hits over the project's research sources."""

    async def search(
        self, *, project_id: UUID, query: str, top_k: int
    ) -> tuple[ResearchHit, ...]: ...


@runtime_checkable
class CompetitorProfilePort(Protocol):
    """Competitor lookup by name (exact first, then prefix)."""

    async def profile(
        self, *, project_id: UUID, name: str
    ) -> CompetitorProfile | None: ...


@runtime_checkable
class AnalyticsFunctionsPort(Protocol):
    """Run one registered analytics metric. Unknown metric names return
    None — the tool converts that into a typed argument rejection."""

    async def run_metric(
        self,
        *,
        project_id: UUID,
        metric: str,
        competitor_ids: tuple[UUID, ...] | None = None,
    ) -> MetricRun | None: ...
