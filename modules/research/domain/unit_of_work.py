"""The research unit of work: the platform's repositories plus research's
own, in one transaction.

Research requires Platform (plan §14.3), so ResearchUnit extends the
platform unit with research repositories. The direction is deliberate:
platform code never imports research, which keeps the research module
disable-able (plan §20).
"""

from typing import Protocol
from uuid import UUID

from modules.platform.domain.unit_of_work import PlatformUnit
from modules.research.domain.entities import Notebook


class Notebooks(Protocol):
    """Notebook repository — every query applies the explicit tenant scope
    (organization_id + project_id), mirroring the Project tag pattern."""

    async def create(self, notebook: Notebook) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, notebook_id: UUID
    ) -> Notebook | None: ...
    async def update(self, notebook: Notebook) -> None: ...
    async def delete(
        self, organization_id: UUID, project_id: UUID, notebook_id: UUID
    ) -> None: ...
    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Notebook]: ...


class ResearchUnit(PlatformUnit, Protocol):
    """One transaction worth of platform + research repositories."""

    notebooks: Notebooks
