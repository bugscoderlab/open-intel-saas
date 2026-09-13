"""SQLAlchemy implementations of the research repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (mirrors the platform contract,
plan §8.2).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.research.domain.entities import (
    Notebook,
    SearchHit,
    Source,
    SourceChunk,
    SourceFile,
)
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


# --- Source files (spec #26, ticket #28) ------------------------------------


def _row_to_source_file(row: Row) -> SourceFile:
    return SourceFile(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        source_id=row.source_id,
        provider=row.provider,
        bucket=row.bucket,
        object_key=row.object_key,
        checksum=row.checksum,
        size_bytes=row.size_bytes,
        content_type=row.content_type,
        created_by=row.created_by,
    )


class SqlSourceFiles:
    """Stored-object registry: the tenant scope is explicit on every query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, source_file: SourceFile) -> None:
        await self._session.execute(
            insert(tables.source_files).values(
                id=source_file.id,
                organization_id=source_file.organization_id,
                project_id=source_file.project_id,
                source_id=source_file.source_id,
                provider=source_file.provider,
                bucket=source_file.bucket,
                object_key=source_file.object_key,
                checksum=source_file.checksum,
                size_bytes=source_file.size_bytes,
                content_type=source_file.content_type,
                created_by=source_file.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, source_file_id: UUID
    ) -> SourceFile | None:
        result = await self._session.execute(
            select(tables.source_files).where(
                tables.source_files.c.organization_id == organization_id,
                tables.source_files.c.project_id == project_id,
                tables.source_files.c.id == source_file_id,
            )
        )
        row = result.first()
        return _row_to_source_file(row) if row else None

    async def get_for_source(
        self, organization_id: UUID, project_id: UUID, source_id: UUID
    ) -> SourceFile | None:
        result = await self._session.execute(
            select(tables.source_files).where(
                tables.source_files.c.organization_id == organization_id,
                tables.source_files.c.project_id == project_id,
                tables.source_files.c.source_id == source_id,
            )
        )
        row = result.first()
        return _row_to_source_file(row) if row else None


# --- Search (ticket #25) ----------------------------------------------------
#
# tsvector / pgvector expressions are impractical through the Core table
# API, so search runs parameterized raw SQL — the tenant scope is in the
# WHERE clause either way, never a post-filter.

_TEXT_SEARCH_SQL = """
select s.id::text as source_id, s.title,
       ts_headline(
           'english', coalesce(s.full_text, ''),
           plainto_tsquery('english', :query),
           'StartSel=<<<,StopSel=>>>'
       ) as snippet,
       ts_rank_cd(
           to_tsvector('english', s.title || ' ' || coalesce(s.full_text, '')),
           plainto_tsquery('english', :query)
       )::float8 as score
from research.sources s
where s.organization_id = cast(:organization_id as uuid)
  and s.project_id = cast(:project_id as uuid)
  and s.status = 'completed'
  and to_tsvector('english', s.title || ' ' || coalesce(s.full_text, ''))
      @@ plainto_tsquery('english', :query)
order by score desc
limit cast(:limit as int)
"""

_VECTOR_SEARCH_SQL = """
select s.id::text as source_id, s.title, c.content as snippet,
       (1 - (c.embedding <=> cast(:query_vector as extensions.vector)))::float8
           as score
from research.source_chunks c
join research.sources s on s.id = c.source_id
where c.organization_id = cast(:organization_id as uuid)
  and c.project_id = cast(:project_id as uuid)
  and c.embedding is not null
order by c.embedding <=> cast(:query_vector as extensions.vector)
limit cast(:limit as int)
"""


def _clean_snippet(snippet: str) -> str:
    return snippet.replace("<<<", "").replace(">>>", "").strip()


def _hit_row(row: dict) -> SearchHit:
    return SearchHit(
        source_id=UUID(row["source_id"]),
        title=row["title"],
        snippet=_clean_snippet(row["snippet"]),
        score=float(row["score"]),
    )


class SqlSearch:
    """Search repository: Postgres-native tsvector full-text and pgvector
    cosine similarity, both scoped to (organization_id, project_id) in
    the query predicate — ranking happens only within the tenant's rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_text(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        result = await self._session.execute(
            text(_TEXT_SEARCH_SQL),
            {
                "organization_id": str(organization_id),
                "project_id": str(project_id),
                "query": query,
                "limit": limit,
            },
        )
        return [_hit_row(dict(row)) for row in result.mappings()]

    async def search_vector(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        query_vector: list[float],
        limit: int,
    ) -> list[SearchHit]:
        literal = "[" + ",".join(repr(float(v)) for v in query_vector) + "]"
        result = await self._session.execute(
            text(_VECTOR_SEARCH_SQL),
            {
                "organization_id": str(organization_id),
                "project_id": str(project_id),
                "query_vector": literal,
                "limit": limit,
            },
        )
        return [_hit_row(dict(row)) for row in result.mappings()]
