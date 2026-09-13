"""SQLAlchemy implementations of the research repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (mirrors the platform contract,
plan §8.2).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.research.domain.entities import Notebook, Source, SourceChunk
from modules.research.infrastructure import db as tables


def _row_to_notebook(row: Row) -> Notebook:
    return Notebook(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        archived=row.archived,
        created_by=row.created_by,
    )


class SqlNotebooks:
    """Notebook repository: the tenant scope is explicit on every query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, notebook: Notebook) -> None:
        await self._session.execute(
            insert(tables.notebooks).values(
                id=notebook.id,
                organization_id=notebook.organization_id,
                project_id=notebook.project_id,
                name=notebook.name,
                description=notebook.description,
                archived=notebook.archived,
                created_by=notebook.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, notebook_id: UUID
    ) -> Notebook | None:
        result = await self._session.execute(
            select(tables.notebooks).where(
                tables.notebooks.c.organization_id == organization_id,
                tables.notebooks.c.project_id == project_id,
                tables.notebooks.c.id == notebook_id,
            )
        )
        row = result.first()
        return _row_to_notebook(row) if row else None

    async def update(self, notebook: Notebook) -> None:
        await self._session.execute(
            update(tables.notebooks)
            .where(
                tables.notebooks.c.organization_id == notebook.organization_id,
                tables.notebooks.c.project_id == notebook.project_id,
                tables.notebooks.c.id == notebook.id,
            )
            .values(
                name=notebook.name,
                description=notebook.description,
                archived=notebook.archived,
                updated_at=datetime.now(UTC),
            )
        )

    async def delete(
        self, organization_id: UUID, project_id: UUID, notebook_id: UUID
    ) -> None:
        await self._session.execute(
            delete(tables.notebooks).where(
                tables.notebooks.c.organization_id == organization_id,
                tables.notebooks.c.project_id == project_id,
                tables.notebooks.c.id == notebook_id,
            )
        )

    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Notebook]:
        result = await self._session.execute(
            select(tables.notebooks)
            .where(
                tables.notebooks.c.organization_id == organization_id,
                tables.notebooks.c.project_id == project_id,
            )
            .order_by(tables.notebooks.c.name)
        )
        return [_row_to_notebook(row) for row in result.all()]


def _row_to_source(row: Row) -> Source:
    return Source(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        notebook_id=row.notebook_id,
        title=row.title,
        type=row.type,
        status=row.status,
        full_text=row.full_text,
        error=row.error,
        created_by=row.created_by,
    )


class SqlSources:
    """Source repository: the tenant scope is explicit on every query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, source: Source) -> None:
        await self._session.execute(
            insert(tables.sources).values(
                id=source.id,
                organization_id=source.organization_id,
                project_id=source.project_id,
                notebook_id=source.notebook_id,
                title=source.title,
                type=source.type,
                status=source.status,
                full_text=source.full_text,
                error=source.error,
                created_by=source.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, source_id: UUID
    ) -> Source | None:
        result = await self._session.execute(
            select(tables.sources).where(
                tables.sources.c.organization_id == organization_id,
                tables.sources.c.project_id == project_id,
                tables.sources.c.id == source_id,
            )
        )
        row = result.first()
        return _row_to_source(row) if row else None

    async def update_status(
        self,
        organization_id: UUID,
        project_id: UUID,
        source_id: UUID,
        *,
        status: str,
        error: str | None,
    ) -> None:
        await self._session.execute(
            update(tables.sources)
            .where(
                tables.sources.c.organization_id == organization_id,
                tables.sources.c.project_id == project_id,
                tables.sources.c.id == source_id,
            )
            .values(status=status, error=error, updated_at=datetime.now(UTC))
        )

    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[Source]:
        result = await self._session.execute(
            select(tables.sources)
            .where(
                tables.sources.c.organization_id == organization_id,
                tables.sources.c.project_id == project_id,
            )
            .order_by(tables.sources.c.created_at)
        )
        return [_row_to_source(row) for row in result.all()]


def _row_to_chunk(row: Row) -> SourceChunk:
    return SourceChunk(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        notebook_id=row.notebook_id,
        source_id=row.source_id,
        chunk_index=row.chunk_index,
        content=row.content,
        embedding=list(row.embedding) if row.embedding is not None else None,
    )


class SqlSourceChunks:
    """Chunk repository: writes are always delete-and-reinsert for the
    whole source, which is what makes pipeline retries idempotent."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_source(
        self,
        organization_id: UUID,
        project_id: UUID,
        source_id: UUID,
        notebook_id: UUID | None,
        chunks: list[SourceChunk],
    ) -> None:
        await self._session.execute(
            delete(tables.source_chunks).where(
                tables.source_chunks.c.organization_id == organization_id,
                tables.source_chunks.c.project_id == project_id,
                tables.source_chunks.c.source_id == source_id,
            )
        )
        if chunks:
            await self._session.execute(
                insert(tables.source_chunks),
                [
                    {
                        "id": chunk.id,
                        "organization_id": organization_id,
                        "project_id": project_id,
                        "notebook_id": notebook_id,
                        "source_id": source_id,
                        "chunk_index": index,
                        "content": chunk.content,
                        "embedding": chunk.embedding,
                    }
                    for index, chunk in enumerate(chunks)
                ],
            )

    async def list_for_source(
        self, organization_id: UUID, project_id: UUID, source_id: UUID
    ) -> list[SourceChunk]:
        result = await self._session.execute(
            select(tables.source_chunks)
            .where(
                tables.source_chunks.c.organization_id == organization_id,
                tables.source_chunks.c.project_id == project_id,
                tables.source_chunks.c.source_id == source_id,
            )
            .order_by(tables.source_chunks.c.chunk_index)
        )
        return [_row_to_chunk(row) for row in result.all()]
