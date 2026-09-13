"""SQLAlchemy research unit of work: the platform's transaction plus
research repositories on the same session.

Subclassing SqlPlatformUnit (rather than duplicating its wiring) keeps
exactly one session/transaction per request: research endpoints and
platform endpoints share commit/rollback semantics, and the research
module stays a one-directional dependency (research → platform only,
plan §14.3).
"""

from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit
from modules.research.domain.unit_of_work import Notebooks
from modules.research.infrastructure.repositories import SqlNotebooks


class SqlResearchUnit(SqlPlatformUnit):
    """One request-scoped transaction: platform repositories plus notebooks."""

    async def __aenter__(self) -> "SqlResearchUnit":
        await super().__aenter__()
        assert self._session is not None
        self.notebooks: Notebooks = SqlNotebooks(self._session)
        return self
