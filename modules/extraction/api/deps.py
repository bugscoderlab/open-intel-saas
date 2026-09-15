"""Request-scoped dependencies for the extraction module.

Identity and authorization come from the platform; the extraction unit
of work arrives through ``app.state.extraction_unit_factory``, wired
only when the module is enabled (plan §20). The SnapshotSource port
arrives through ``app.state.extraction_snapshot_source`` (composition
root), mirroring how collection receives its fetcher.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from modules.extraction.domain.ports import SnapshotSource
from modules.extraction.domain.unit_of_work import ExtractionUnit
from modules.platform.api.deps import (  # noqa: F401  (re-exported)
    AuthzDep,
    PrincipalDep,
    get_authz,
    get_principal,
    map_error,
)
from modules.platform.application.errors import PlatformError


async def get_extraction_unit(request: Request) -> AsyncIterator[ExtractionUnit]:
    """One transaction per request: commit on success, rollback on error.
    Mirrors the collection unit dependency exactly."""
    factory = request.app.state.extraction_unit_factory
    unit = factory()
    async with unit:
        try:
            yield unit
        except PlatformError:
            await unit.rollback()
            raise
        await unit.commit()


async def get_snapshot_source(request: Request) -> SnapshotSource:
    return request.app.state.extraction_snapshot_source


ExtractionUnitDep = Annotated[ExtractionUnit, Depends(get_extraction_unit)]
SnapshotSourceDep = Annotated[SnapshotSource, Depends(get_snapshot_source)]

__all__ = [
    "PrincipalDep",
    "AuthzDep",
    "ExtractionUnitDep",
    "SnapshotSourceDep",
    "get_principal",
    "get_authz",
    "get_extraction_unit",
    "get_snapshot_source",
    "map_error",
]
