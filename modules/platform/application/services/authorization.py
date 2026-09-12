"""The centralized authorization service (ticket #4, plan §8.3).

One service answers "does this principal hold this Permission at this
scope": it loads the membership chain (explicit project role →
team-derived role → organization role), resolves most-specific-scope-wins
through the domain matrix, and raises typed errors. Route code references
role names nowhere.
"""

from uuid import UUID

from modules.platform.application.errors import ForbiddenError, NotFoundError
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import (
    can_change_role,
    holds,
    resolve_role,
)


class AuthorizationService:
    """Permission checks against a unit of work."""

    def __init__(self, unit: PlatformUnit) -> None:
        self._unit = unit

    async def resolved_role(
        self,
        principal: Principal,
        *,
        organization_id: UUID,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> str | None:
        """Resolve the matrix Role for the principal at this scope, or None
        when they hold no membership in the chain."""
        membership = await self._unit.memberships.get(
            organization_id, principal.app_user_id
        )
        if membership is None:
            return None
        team_role = None
        if team_id is not None:
            team_membership = await self._unit.team_memberships.get(
                team_id, principal.app_user_id
            )
            if team_membership is not None:
                team_role = team_membership.role
        project_role = None
        if project_id is not None:
            project_membership = await self._unit.project_memberships.get(
                project_id, principal.app_user_id
            )
            if project_membership is not None:
                project_role = project_membership.role
        return resolve_role(
            org_role=membership.role,
            team_role=team_role,
            project_role=project_role,
        )

    async def require(
        self,
        principal: Principal,
        permission: str,
        *,
        organization_id: UUID,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> str:
        """Require the Permission at this scope; return the resolved Role.

        Raises:
            NotFoundError: The principal is not a member of the
                organization — the tenant-safe answer to guessed IDs.
            ForbiddenError: Member, but the matrix does not grant the
                Permission.
        """
        membership = await self._unit.memberships.get(
            organization_id, principal.app_user_id
        )
        if membership is None:
            raise NotFoundError("organization not found")
        role = await self.resolved_role(
            principal,
            organization_id=organization_id,
            team_id=team_id,
            project_id=project_id,
        )
        if not holds(role, permission):
            raise ForbiddenError(f"missing permission: {permission}")
        assert role is not None
        return role

    async def require_org_role(
        self,
        principal: Principal,
        *,
        organization_id: UUID,
    ) -> str:
        """Require plain organization membership; return the org role name."""
        membership = await self._unit.memberships.get(
            organization_id, principal.app_user_id
        )
        if membership is None:
            raise NotFoundError("organization not found")
        return membership.role

    async def can_change_member_role(
        self,
        principal: Principal,
        *,
        organization_id: UUID,
        target_app_user_id: UUID,
    ) -> None:
        """member.change_role with the owner-over-admins gate (ticket #4)."""
        actor_role = await self.require_org_role(
            principal, organization_id=organization_id
        )
        target = await self._unit.memberships.get(organization_id, target_app_user_id)
        if target is None:
            raise NotFoundError("member not found")
        if not can_change_role(actor_org_role=actor_role, target_org_role=target.role):
            raise ForbiddenError("cannot change this member's role")
