"""SQLAlchemy competitor unit of work: the platform's transaction plus
competitor repositories on the same session (mirrors SqlResearchUnit).
"""

from modules.competitor_intelligence.domain.unit_of_work import (
    Competitors,
    CompetitorUnit,
    Locations,
)
from modules.competitor_intelligence.infrastructure.repositories import (
    SqlCompetitors,
    SqlLocations,
)
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit


class SqlCompetitorUnit(SqlPlatformUnit):
    """One request-scoped transaction: platform repositories plus
    competitors and locations."""

    async def __aenter__(self) -> "SqlCompetitorUnit":
        await super().__aenter__()
        assert self._session is not None
        self.competitors: Competitors = SqlCompetitors(self._session)
        self.locations: Locations = SqlLocations(self._session)
        return self


__all__ = ["CompetitorUnit", "SqlCompetitorUnit"]
