"""SQLAlchemy collection unit of work: the platform's transaction plus
collection repositories on the same session (mirrors SqlCompetitorUnit).
"""

from modules.collection.domain.unit_of_work import CollectionUnit, Jobs, Snapshots
from modules.collection.infrastructure.repositories import SqlJobs, SqlSnapshots
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit


class SqlCollectionUnit(SqlPlatformUnit):
    """One request-scoped transaction: platform repositories plus
    snapshots and jobs."""

    async def __aenter__(self) -> "SqlCollectionUnit":
        await super().__aenter__()
        assert self._session is not None
        self.snapshots: Snapshots = SqlSnapshots(self._session)
        self.jobs: Jobs = SqlJobs(self._session)
        return self


__all__ = ["CollectionUnit", "SqlCollectionUnit"]
