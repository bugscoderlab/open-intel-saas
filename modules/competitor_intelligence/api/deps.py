"""Request-scoped dependencies for the competitor-intelligence module.

Identity and authorization come from the platform (competitors requires
Platform, plan §14.3); the competitor unit of work arrives through
``app.state.competitor_unit_factory``, wired only when the module is
enabled (plan §20) — mirroring the research deps exactly.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from modules.competitor_intelligence.domain.unit_of_work import CompetitorUnit
from modules.platform.api.deps import (  # noqa: F401  (re-exported)
    AuthzDep,
    PrincipalDep,
    get_authz,
    get_principal,
    map_error,
)
from modules.platform.application.errors import PlatformError


async def get_competitor_unit(request: Request) -> AsyncIterator[CompetitorUnit]:
    """One transaction per request: commit on success, rollback on error.
    Mirrors the platform/research unit dependency exactly."""
    factory = request.app.state.competitor_unit_factory
    unit = factory()
    async with unit:
        try:
            yield unit
        except PlatformError:
            await unit.rollback()
            raise
        await unit.commit()


CompetitorUnitDep = Annotated[CompetitorUnit, Depends(get_competitor_unit)]

__all__ = [
    "PrincipalDep",
    "AuthzDep",
    "CompetitorUnitDep",
    "get_principal",
    "get_authz",
    "get_competitor_unit",
    "map_error",
]
