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

from modules.research.domain.entities import Notebook
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
