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

__all__ = [
    "PrincipalDep",
    "AuthzDep",
    "ResearchUnitDep",
    "get_principal",
    "get_authz",
    "get_research_unit",
    "map_error",
]
