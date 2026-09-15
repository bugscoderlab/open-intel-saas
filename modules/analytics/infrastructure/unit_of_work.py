"""SQLAlchemy analytics unit of work: the platform transaction under a
module-shaped seam (mirrors the other modules' units; no extra
repositories — analytics owns no tables)."""

from modules.analytics.domain.unit_of_work import AnalyticsUnit
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit


class SqlAnalyticsUnit(SqlPlatformUnit):
    async def __aenter__(self) -> "SqlAnalyticsUnit":
        await super().__aenter__()
        return self


__all__ = ["AnalyticsUnit", "SqlAnalyticsUnit"]
