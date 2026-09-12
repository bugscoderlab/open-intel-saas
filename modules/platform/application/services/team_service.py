"""Team use cases (ticket #7). Any organization member can create a Team
and becomes its manager. Team membership implies access to team-owned
projects through the matrix — never denormalized grants.
"""

from uuid import UUID, uuid4

from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.entities import AuditEntry, Team, TeamMembership
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def create_team(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
    name: str,
) -> Team:
    """Create a Team; the creator becomes its manager."""
    await authz.require(
        principal, Permission.TEAM_CREATE, organization_id=organization_id
    )
    team = Team(
        id=uuid4(),
        organization_id=organization_id,
        name=name,
        created_by=principal.app_user_id,
    )
    await unit.teams.create(team)
    await unit.team_memberships.add(
        TeamMembership(
            team_id=team.id, app_user_id=principal.app_user_id, role="manager"
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="team.create",
            target_type="team",
            target_id=str(team.id),
            organization_id=organization_id,
            payload={"name": name},
        )
    )
    return team


async def list_teams(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
) -> list[Team]:
    await authz.require(principal, Permission.ORG_READ, organization_id=organization_id)
    return await unit.teams.list_for_organization(organization_id)


async def get_team(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    team_id: UUID,
) -> Team:
    team = await unit.teams.get(team_id)
    if team is None:
        raise NotFoundError("team not found")
    await authz.require(
        principal,
        Permission.TEAM_READ,
        organization_id=team.organization_id,
        team_id=team_id,
    )
    return team


async def update_team(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    team_id: UUID,
    name: str,
) -> Team:
    team = await unit.teams.get(team_id)
    if team is None:
        raise NotFoundError("team not found")
    await authz.require(
        principal,
        Permission.TEAM_UPDATE,
        organization_id=team.organization_id,
        team_id=team_id,
    )
    updated = Team(
        id=team.id,
        organization_id=team.organization_id,
        name=name,
        created_by=team.created_by,
    )
    await unit.teams.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="team.update",
            target_type="team",
            target_id=str(team_id),
            organization_id=team.organization_id,
            payload={"name": name},
        )
    )
    return updated


async def delete_team(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    team_id: UUID,
) -> None:
    team = await unit.teams.get(team_id)
    if team is None:
        raise NotFoundError("team not found")
    await authz.require(
        principal,
        Permission.TEAM_DELETE,
        organization_id=team.organization_id,
        team_id=team_id,
    )
    await unit.teams.delete(team_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="team.delete",
            target_type="team",
            target_id=str(team_id),
            organization_id=team.organization_id,
            payload={},
        )
    )


async def list_team_members(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    team_id: UUID,
) -> list[TeamMembership]:
    team = await unit.teams.get(team_id)
    if team is None:
        raise NotFoundError("team not found")
    await authz.require(
        principal,
        Permission.TEAM_READ,
        organization_id=team.organization_id,
        team_id=team_id,
    )
    return await unit.team_memberships.list(team_id)


async def remove_team_member(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    team_id: UUID,
    target_app_user_id: UUID,
) -> None:
    team = await unit.teams.get(team_id)
    if team is None:
        raise NotFoundError("team not found")
    await authz.require(
        principal,
        Permission.TEAM_MEMBER_REMOVE,
        organization_id=team.organization_id,
        team_id=team_id,
    )
    target = await unit.team_memberships.get(team_id, target_app_user_id)
    if target is None:
        raise NotFoundError("team member not found")
    await unit.team_memberships.remove(team_id, target_app_user_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="team.member_remove",
            target_type="team_member",
            target_id=str(target_app_user_id),
            organization_id=team.organization_id,
            payload={"team_id": str(team_id)},
        )
    )
