"""SQLAlchemy implementations of the repository protocols.

Tenant scoping lives here, in one enforced layer: every query that
touches tenant-owned data filters by the explicit scope passed in. The
service layer derives that scope from rows it has already authorized;
client-supplied IDs can never widen it (ticket #8 acceptance).

The service connection is the database owner and bypasses RLS — which is
exactly why these filters are load-bearing, not decorative (plan §8.2).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from modules.platform.domain.entities import (
    AppUser,
    AuditEntry,
    Invitation,
    Membership,
    Organization,
    OutboxEvent,
    Project,
    ProjectMembership,
    ProjectTag,
    Team,
    TeamMembership,
)
from modules.platform.infrastructure import db as tables


def _row_to_org(row: Row) -> Organization:
    return Organization(id=row.id, name=row.name, created_by=row.created_by)


def _row_to_membership(row: Row) -> Membership:
    return Membership(
        organization_id=row.organization_id,
        app_user_id=row.app_user_id,
        role=row.role,
    )


def _row_to_team(row: Row) -> Team:
    return Team(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        created_by=row.created_by,
    )


def _row_to_team_membership(row: Row) -> TeamMembership:
    return TeamMembership(
        team_id=row.team_id, app_user_id=row.app_user_id, role=row.role
    )


def _row_to_project(row: Row) -> Project:
    return Project(
        id=row.id,
        organization_id=row.organization_id,
        owning_team_id=row.owning_team_id,
        name=row.name,
        visibility=row.visibility,
        created_by=row.created_by,
    )


def _row_to_project_membership(row: Row) -> ProjectMembership:
    return ProjectMembership(
        project_id=row.project_id, app_user_id=row.app_user_id, role=row.role
    )


def _row_to_tag(row: Row) -> ProjectTag:
    return ProjectTag(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        name=row.name,
        color=row.color,
        created_by=row.created_by,
    )


def _row_to_invitation(row: Row) -> Invitation:
    return Invitation(
        id=row.id,
        organization_id=row.organization_id,
        scope=row.scope,
        team_id=row.team_id,
        project_id=row.project_id,
        email=row.email,
        role=row.role,
        token_hash=row.token_hash,
        invited_by=row.invited_by,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )


class SqlAppUsers:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, app_user_id: UUID) -> AppUser | None:
        result = await self._session.execute(
            select(tables.app_users).where(tables.app_users.c.id == app_user_id)
        )
        row = result.first()
        if row is None:
            return None
        return AppUser(
            id=row.id,
            email=row.email,
            display_name=row.display_name,
            status=row.status,
        )

    async def get_id_by_email(self, email: str) -> UUID | None:
        result = await self._session.execute(
            select(tables.app_users.c.id).where(
                func.lower(tables.app_users.c.email) == email.lower()
            )
        )
        return result.scalar_one_or_none()


class SqlOrganizations:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, organization: Organization) -> None:
        await self._session.execute(
            insert(tables.organizations).values(
                id=organization.id,
                name=organization.name,
                created_by=organization.created_by,
            )
        )

    async def get(self, organization_id: UUID) -> Organization | None:
        result = await self._session.execute(
            select(tables.organizations).where(
                tables.organizations.c.id == organization_id
            )
        )
        row = result.first()
        return _row_to_org(row) if row else None

    async def update(self, organization: Organization) -> None:
        await self._session.execute(
            update(tables.organizations)
            .where(tables.organizations.c.id == organization.id)
            .values(name=organization.name, updated_at=datetime.now(UTC))
        )

    async def delete(self, organization_id: UUID) -> None:
        await self._session.execute(
            delete(tables.organizations).where(
                tables.organizations.c.id == organization_id
            )
        )

    async def list_for_user(self, app_user_id: UUID) -> list[Organization]:
        result = await self._session.execute(
            select(tables.organizations)
            .join(
                tables.organization_members,
                tables.organization_members.c.organization_id
                == tables.organizations.c.id,
            )
            .where(tables.organization_members.c.app_user_id == app_user_id)
            .order_by(tables.organizations.c.created_at)
        )
        return [_row_to_org(row) for row in result.all()]


class SqlMemberships:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID, app_user_id: UUID) -> Membership | None:
        result = await self._session.execute(
            select(tables.organization_members).where(
                tables.organization_members.c.organization_id == organization_id,
                tables.organization_members.c.app_user_id == app_user_id,
            )
        )
        row = result.first()
        return _row_to_membership(row) if row else None

    async def list(self, organization_id: UUID) -> list[Membership]:
        result = await self._session.execute(
            select(tables.organization_members)
            .where(tables.organization_members.c.organization_id == organization_id)
            .order_by(tables.organization_members.c.created_at)
        )
        return [_row_to_membership(row) for row in result.all()]

    async def add(self, membership: Membership) -> None:
        await self._session.execute(
            insert(tables.organization_members).values(
                organization_id=membership.organization_id,
                app_user_id=membership.app_user_id,
                role=membership.role,
            )
        )

    async def update_role(
        self, organization_id: UUID, app_user_id: UUID, role: str
    ) -> None:
        await self._session.execute(
            update(tables.organization_members)
            .where(
                tables.organization_members.c.organization_id == organization_id,
                tables.organization_members.c.app_user_id == app_user_id,
            )
            .values(role=role)
        )

    async def remove(self, organization_id: UUID, app_user_id: UUID) -> None:
        await self._session.execute(
            delete(tables.organization_members).where(
                tables.organization_members.c.organization_id == organization_id,
                tables.organization_members.c.app_user_id == app_user_id,
            )
        )

    async def count_role(self, organization_id: UUID, role: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(tables.organization_members)
            .where(
                tables.organization_members.c.organization_id == organization_id,
                tables.organization_members.c.role == role,
            )
        )
        return int(result.scalar_one())


class SqlTeams:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, team: Team) -> None:
        await self._session.execute(
            insert(tables.teams).values(
                id=team.id,
                organization_id=team.organization_id,
                name=team.name,
                created_by=team.created_by,
            )
        )

    async def get(self, team_id: UUID) -> Team | None:
        result = await self._session.execute(
            select(tables.teams).where(tables.teams.c.id == team_id)
        )
        row = result.first()
        return _row_to_team(row) if row else None

    async def update(self, team: Team) -> None:
        await self._session.execute(
            update(tables.teams)
            .where(tables.teams.c.id == team.id)
            .values(name=team.name, updated_at=datetime.now(UTC))
        )

    async def delete(self, team_id: UUID) -> None:
        await self._session.execute(
            delete(tables.teams).where(tables.teams.c.id == team_id)
        )

    async def list_for_organization(self, organization_id: UUID) -> list[Team]:
        result = await self._session.execute(
            select(tables.teams)
            .where(tables.teams.c.organization_id == organization_id)
            .order_by(tables.teams.c.created_at)
        )
        return [_row_to_team(row) for row in result.all()]


class SqlTeamMemberships:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, team_id: UUID, app_user_id: UUID) -> TeamMembership | None:
        result = await self._session.execute(
            select(tables.team_members).where(
                tables.team_members.c.team_id == team_id,
                tables.team_members.c.app_user_id == app_user_id,
            )
        )
        row = result.first()
        return _row_to_team_membership(row) if row else None

    async def list(self, team_id: UUID) -> list[TeamMembership]:
        result = await self._session.execute(
            select(tables.team_members)
            .where(tables.team_members.c.team_id == team_id)
            .order_by(tables.team_members.c.created_at)
        )
        return [_row_to_team_membership(row) for row in result.all()]

    async def add(self, membership: TeamMembership) -> None:
        await self._session.execute(
            insert(tables.team_members).values(
                team_id=membership.team_id,
                app_user_id=membership.app_user_id,
                role=membership.role,
            )
        )

    async def remove(self, team_id: UUID, app_user_id: UUID) -> None:
        await self._session.execute(
            delete(tables.team_members).where(
                tables.team_members.c.team_id == team_id,
                tables.team_members.c.app_user_id == app_user_id,
            )
        )


class SqlProjects:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, project: Project) -> None:
        await self._session.execute(
            insert(tables.projects).values(
                id=project.id,
                organization_id=project.organization_id,
                owning_team_id=project.owning_team_id,
                name=project.name,
                visibility=project.visibility,
                created_by=project.created_by,
            )
        )

    async def get(self, project_id: UUID) -> Project | None:
        result = await self._session.execute(
            select(tables.projects).where(tables.projects.c.id == project_id)
        )
        row = result.first()
        return _row_to_project(row) if row else None

    async def update(self, project: Project) -> None:
        await self._session.execute(
            update(tables.projects)
            .where(tables.projects.c.id == project.id)
            .values(
                name=project.name,
                visibility=project.visibility,
                updated_at=datetime.now(UTC),
            )
        )

    async def delete(self, project_id: UUID) -> None:
        await self._session.execute(
            delete(tables.projects).where(tables.projects.c.id == project_id)
        )

    async def list_for_organization(self, organization_id: UUID) -> list[Project]:
        result = await self._session.execute(
            select(tables.projects)
            .where(tables.projects.c.organization_id == organization_id)
            .order_by(tables.projects.c.created_at)
        )
        return [_row_to_project(row) for row in result.all()]


class SqlProjectMemberships:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, project_id: UUID, app_user_id: UUID
    ) -> ProjectMembership | None:
        result = await self._session.execute(
            select(tables.project_members).where(
                tables.project_members.c.project_id == project_id,
                tables.project_members.c.app_user_id == app_user_id,
            )
        )
        row = result.first()
        return _row_to_project_membership(row) if row else None

    async def list(self, project_id: UUID) -> list[ProjectMembership]:
        result = await self._session.execute(
            select(tables.project_members)
            .where(tables.project_members.c.project_id == project_id)
            .order_by(tables.project_members.c.created_at)
        )
        return [_row_to_project_membership(row) for row in result.all()]

    async def add(self, membership: ProjectMembership) -> None:
        await self._session.execute(
            insert(tables.project_members).values(
                project_id=membership.project_id,
                app_user_id=membership.app_user_id,
                role=membership.role,
            )
        )

    async def remove(self, project_id: UUID, app_user_id: UUID) -> None:
        await self._session.execute(
            delete(tables.project_members).where(
                tables.project_members.c.project_id == project_id,
                tables.project_members.c.app_user_id == app_user_id,
            )
        )


class SqlTags:
    """Project tag repository: the tenant scope is explicit on every query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tag: ProjectTag) -> None:
        await self._session.execute(
            insert(tables.project_tags).values(
                id=tag.id,
                organization_id=tag.organization_id,
                project_id=tag.project_id,
                name=tag.name,
                color=tag.color,
                created_by=tag.created_by,
            )
        )

    async def get(
        self, organization_id: UUID, project_id: UUID, tag_id: UUID
    ) -> ProjectTag | None:
        result = await self._session.execute(
            select(tables.project_tags).where(
                tables.project_tags.c.organization_id == organization_id,
                tables.project_tags.c.project_id == project_id,
                tables.project_tags.c.id == tag_id,
            )
        )
        row = result.first()
        return _row_to_tag(row) if row else None

    async def update(self, tag: ProjectTag) -> None:
        await self._session.execute(
            update(tables.project_tags)
            .where(
                tables.project_tags.c.organization_id == tag.organization_id,
                tables.project_tags.c.project_id == tag.project_id,
                tables.project_tags.c.id == tag.id,
            )
            .values(name=tag.name, color=tag.color, updated_at=datetime.now(UTC))
        )

    async def delete(
        self, organization_id: UUID, project_id: UUID, tag_id: UUID
    ) -> None:
        await self._session.execute(
            delete(tables.project_tags).where(
                tables.project_tags.c.organization_id == organization_id,
                tables.project_tags.c.project_id == project_id,
                tables.project_tags.c.id == tag_id,
            )
        )

    async def list_for_project(
        self, organization_id: UUID, project_id: UUID
    ) -> list[ProjectTag]:
        result = await self._session.execute(
            select(tables.project_tags)
            .where(
                tables.project_tags.c.organization_id == organization_id,
                tables.project_tags.c.project_id == project_id,
            )
            .order_by(tables.project_tags.c.name)
        )
        return [_row_to_tag(row) for row in result.all()]


class SqlInvitations:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, invitation: Invitation) -> None:
        await self._session.execute(
            insert(tables.invitations).values(
                id=invitation.id,
                organization_id=invitation.organization_id,
                scope=invitation.scope,
                team_id=invitation.team_id,
                project_id=invitation.project_id,
                email=invitation.email,
                role=invitation.role,
                token_hash=invitation.token_hash,
                invited_by=invitation.invited_by,
                expires_at=invitation.expires_at,
            )
        )

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        result = await self._session.execute(
            select(tables.invitations).where(
                tables.invitations.c.token_hash == token_hash
            )
        )
        row = result.first()
        return _row_to_invitation(row) if row else None

    async def consume(self, invitation_id: UUID) -> bool:
        """Single-use claim: one UPDATE ... WHERE consumed_at IS NULL; the
        rowcount tells exactly one racer they won."""
        result = await self._session.execute(
            update(tables.invitations)
            .where(
                tables.invitations.c.id == invitation_id,
                tables.invitations.c.consumed_at.is_(None),
                tables.invitations.c.expires_at > datetime.now(UTC),
            )
            .values(consumed_at=datetime.now(UTC))
        )
        return result.rowcount == 1  # type: ignore[attr-defined]


class SqlAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, entry: AuditEntry) -> None:
        await self._session.execute(
            insert(tables.audit_log).values(
                actor_id=entry.actor_id,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                organization_id=entry.organization_id,
                payload=entry.payload,
            )
        )


class SqlOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OutboxEvent) -> None:
        await self._session.execute(
            insert(tables.outbox_events).values(
                id=uuid4(), event_type=event.event_type, payload=event.payload
            )
        )
