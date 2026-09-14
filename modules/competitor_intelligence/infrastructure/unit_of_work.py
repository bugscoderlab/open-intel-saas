"""SQLAlchemy competitor unit of work: the platform's transaction plus
competitor repositories on the same session (mirrors SqlResearchUnit).
"""

from modules.competitor_intelligence.domain.unit_of_work import (
    Competitors,
    CompetitorUnit,
    Evidence,
    Locations,
    Observations,
    Services,
)
from modules.competitor_intelligence.infrastructure.repositories import (
    SqlCompetitors,
    SqlEvidence,
    SqlLocations,
    SqlObservations,
    SqlServices,
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
        self.services: Services = SqlServices(self._session)
        self.observations: Observations = SqlObservations(self._session)
        self.evidence: Evidence = SqlEvidence(self._session)
        return self


__all__ = ["CompetitorUnit", "SqlCompetitorUnit"]
