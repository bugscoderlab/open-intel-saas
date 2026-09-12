"""SQLAlchemy unit of work: all repositories on one session/transaction."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from modules.platform.domain.unit_of_work import (
    AppUsers,
    AuditLog,
    Invitations,
    Memberships,
    Organizations,
    Outbox,
    ProjectMemberships,
    Projects,
    Tags,
    TeamMemberships,
    Teams,
)
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
        self.app_users: AppUsers = SqlAppUsers(self._session)
        self.organizations: Organizations = SqlOrganizations(self._session)
        self.memberships: Memberships = SqlMemberships(self._session)
        self.teams: Teams = SqlTeams(self._session)
        self.team_memberships: TeamMemberships = SqlTeamMemberships(self._session)
        self.projects: Projects = SqlProjects(self._session)
        self.project_memberships: ProjectMemberships = SqlProjectMemberships(
            self._session
        )
        self.tags: Tags = SqlTags(self._session)
        self.invitations: Invitations = SqlInvitations(self._session)
        self.audit: AuditLog = SqlAuditLog(self._session)
        self.outbox: Outbox = SqlOutbox(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
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
