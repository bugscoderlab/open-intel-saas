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
from modules.research.domain.entities import Notebook, SearchHit, Source, SourceChunk


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


class Sources(Protocol):
    """Source repository — the tenant scope is explicit on every query."""

    async def create(self, source: Source) -> None: ...
    async def get(
        self, organization_id: UUID, project_id: UUID, source_id: UUID
    ) -> Source | None: ...
    async def update_status(
        self,
        organization_id: UUID,
        project_id: UUID,
        source_id: UUID,
        *,
        status: str,
        error: str | None,
    ) -> None: ...
    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Source]: ...


class SourceChunks(Protocol):
    """Chunk repository. The pipeline writes chunks as one
    delete-and-reinsert operation so reprocessing a Source is idempotent
    under repeated execution (mirroring upstream embed_source)."""

    async def replace_for_source(
        self,
        organization_id: UUID,
        project_id: UUID,
        source_id: UUID,
        notebook_id: UUID | None,
        chunks: list[SourceChunk],
    ) -> None: ...
    async def list_for_source(
        self, organization_id: UUID, project_id: UUID, source_id: UUID
    ) -> list[SourceChunk]: ...


class Search(Protocol):
    """Tenant-scoped search (ticket #25). The scope is a mandatory query
    predicate on every search — authorization happens BEFORE retrieval,
    similarity/ranking is computed only within the tenant's rows."""

    async def search_text(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...
    async def search_vector(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        query_vector: list[float],
        limit: int,
    ) -> list[SearchHit]: ...


class ResearchUnit(PlatformUnit, Protocol):
    """One transaction worth of platform + research repositories."""

    notebooks: Notebooks
    sources: Sources
    source_chunks: SourceChunks
    search: Search
