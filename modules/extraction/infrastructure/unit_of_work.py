"""SQLAlchemy extraction unit of work: the platform's transaction plus
extraction repositories on the same session (mirrors SqlCollectionUnit).
"""

from modules.extraction.domain.unit_of_work import ExtractionRuns, ExtractionUnit
from modules.extraction.infrastructure.repositories import SqlExtractionRuns
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit


class SqlExtractionUnit(SqlPlatformUnit):
    """One request-scoped transaction: platform repositories plus
    extraction runs."""

    async def __aenter__(self) -> "SqlExtractionUnit":
        await super().__aenter__()
        assert self._session is not None
        self.extraction_runs: ExtractionRuns = SqlExtractionRuns(self._session)
        return self


__all__ = ["ExtractionUnit", "SqlExtractionUnit"]
