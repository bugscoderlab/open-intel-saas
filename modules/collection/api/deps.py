"""Request-scoped dependencies for the collection module.

Identity and authorization come from the platform; the collection unit
of work arrives through ``app.state.collection_unit_factory``, wired
only when the module is enabled (plan §20) — mirroring the research and
competitor deps exactly.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from modules.collection.domain.unit_of_work import CollectionUnit
from modules.platform.api.deps import (  # noqa: F401  (re-exported)
    AuthzDep,
    PrincipalDep,
    get_authz,
    get_principal,
    map_error,
)
from modules.platform.application.errors import PlatformError


async def get_collection_unit(request: Request) -> AsyncIterator[CollectionUnit]:
    """One transaction per request: commit on success, rollback on error.
    Mirrors the platform/research/competitor unit dependency exactly."""
    factory = request.app.state.collection_unit_factory
    unit = factory()
    async with unit:
        try:
            yield unit
        except PlatformError:
            await unit.rollback()
            raise
        await unit.commit()


CollectionUnitDep = Annotated[CollectionUnit, Depends(get_collection_unit)]

__all__ = [
    "PrincipalDep",
    "AuthzDep",
    "CollectionUnitDep",
    "get_principal",
    "get_authz",
    "get_collection_unit",
    "map_error",
]
