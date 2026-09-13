"""Request-scoped dependencies for the research module.

Identity and authorization come from the platform (research requires
Platform, plan §14.3); the research unit of work is provided by the
composition root through ``app.state.research_unit_factory`` and is only
wired when the research module is enabled (plan §20).
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from modules.platform.api.deps import (
    AuthzDep,  # noqa: F401  (re-exported for research routers)
    PrincipalDep,  # noqa: F401
    get_authz,
    get_principal,
    map_error,
)
from modules.platform.application.errors import PlatformError
from modules.research.domain.embedder import Embedder
from modules.research.domain.unit_of_work import ResearchUnit


async def get_research_unit(request: Request) -> AsyncIterator[ResearchUnit]:
    """One transaction per request: commit on success, rollback on error.
    Mirrors the platform unit dependency exactly."""
    factory = request.app.state.research_unit_factory
    unit = factory()
    async with unit:
        try:
            yield unit
        except PlatformError:
            await unit.rollback()
            raise
        await unit.commit()


ResearchUnitDep = Annotated[ResearchUnit, Depends(get_research_unit)]


async def get_search_embedder(request: Request) -> Embedder | None:
    """The pipeline's embedder, provided by the composition root on
    app.state (Esperanto in serve.py, a deterministic fake in tests).

    Returns None when absent rather than raising: FastAPI resolves
    dependencies outside the @endpoint error wrapper, so a raise here
    would escape as a bare 500. The service turns None into a typed
    503 inside the wrapper's reach."""
    return getattr(request.app.state, "research_embedder", None)


SearchEmbedderDep = Annotated[Embedder, Depends(get_search_embedder)]

__all__ = [
    "PrincipalDep",
    "AuthzDep",
    "ResearchUnitDep",
    "SearchEmbedderDep",
    "get_principal",
    "get_authz",
    "get_research_unit",
    "get_search_embedder",
    "map_error",
]
