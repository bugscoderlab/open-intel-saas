"""SQLAlchemy unit of work: all repositories on one session/transaction."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from modules.platform.infrastructure.db import create_session
from modules.platform.infrastructure.repositories import (
    SqlAppUsers,
    SqlAuditLog,
    SqlInvitations,
    SqlMemberships,
    SqlOrganizations,
    SqlOutbox,
    SqlProjectMemberships,
    SqlProjects,
    SqlTags,
    SqlTeamMemberships,
    SqlTeams,
)


class SqlPlatformUnit:
    """One request-scoped transaction.

    Usage (API layer)::

        async with unit:
            ...services...
            await unit.commit()
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlPlatformUnit":
        self._session = create_session(self._engine)
        await self._session.begin()
        self.app_users = SqlAppUsers(self._session)
        self.organizations = SqlOrganizations(self._session)
        self.memberships = SqlMemberships(self._session)
        self.teams = SqlTeams(self._session)
        self.team_memberships = SqlTeamMemberships(self._session)
        self.projects = SqlProjects(self._session)
        self.project_memberships = SqlProjectMemberships(self._session)
        self.tags = SqlTags(self._session)
        self.invitations = SqlInvitations(self._session)
        self.audit = SqlAuditLog(self._session)
        self.outbox = SqlOutbox(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            if exc_type is not None and self._session.is_active:
                await self._session.rollback()
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None and self._session.is_active:
            await self._session.rollback()
