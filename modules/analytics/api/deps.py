"""Request-scoped dependencies for the analytics module. Mirrors the
collection/extraction deps: one unit per request, and the
ApprovedFactsSource port from app.state (composition root)."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from modules.analytics.domain.ports import ApprovedFactsSource
from modules.analytics.domain.unit_of_work import AnalyticsUnit
from modules.platform.api.deps import (  # noqa: F401  (re-exported)
    AuthzDep,
    PrincipalDep,
    get_authz,
    get_principal,
    map_error,
)
from modules.platform.application.errors import PlatformError


async def get_analytics_unit(request: Request) -> AsyncIterator[AnalyticsUnit]:
    """One transaction per request: commit on success, rollback on error."""
    factory = request.app.state.analytics_unit_factory
    unit = factory()
    async with unit:
        try:
            yield unit
        except PlatformError:
            await unit.rollback()
            raise
        await unit.commit()


async def get_facts_source(request: Request) -> ApprovedFactsSource:
    return request.app.state.analytics_facts_source


AnalyticsUnitDep = Annotated[AnalyticsUnit, Depends(get_analytics_unit)]
FactsSourceDep = Annotated[ApprovedFactsSource, Depends(get_facts_source)]

__all__ = [
    "PrincipalDep",
    "AuthzDep",
    "AnalyticsUnitDep",
    "FactsSourceDep",
    "get_principal",
    "get_authz",
    "get_analytics_unit",
    "get_facts_source",
    "map_error",
]
