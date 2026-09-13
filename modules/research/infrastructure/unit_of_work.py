"""SQLAlchemy research unit of work: the platform's transaction plus
research repositories on the same session.

Subclassing SqlPlatformUnit (rather than duplicating its wiring) keeps
exactly one session/transaction per request: research endpoints and
platform endpoints share commit/rollback semantics, and the research
module stays a one-directional dependency (research → platform only,
plan §14.3).
"""

from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit
from modules.research.domain.unit_of_work import (
    Notebooks,
    Search,
    SourceChunks,
    Sources,
)
from modules.research.infrastructure.repositories import (
    SqlNotebooks,
    SqlSearch,
    SqlSourceChunks,
    SqlSources,
)


class SqlResearchUnit(SqlPlatformUnit):
    """One request-scoped transaction: platform repositories plus notebooks
    and sources."""

    async def __aenter__(self) -> "SqlResearchUnit":
        await super().__aenter__()
        assert self._session is not None
        self.notebooks: Notebooks = SqlNotebooks(self._session)
        self.sources: Sources = SqlSources(self._session)
        self.source_chunks: SourceChunks = SqlSourceChunks(self._session)
        self.search: Search = SqlSearch(self._session)
        return self
