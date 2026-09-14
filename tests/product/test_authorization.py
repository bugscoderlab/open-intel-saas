"""Unit seam: the Permission matrix + most-specific-scope-wins resolution
(ticket #4 acceptance, case by case — pure domain, no database).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    can_change_role,
    holds,
    resolve_role,
)

ORG_PERMS = {
    Permission.ORG_READ,
    Permission.ORG_UPDATE,
    Permission.ORG_DELETE,
    Permission.MEMBER_LIST,
    Permission.MEMBER_INVITE,
    Permission.MEMBER_REMOVE,
    Permission.MEMBER_CHANGE_ROLE,
    Permission.TEAM_CREATE,
    Permission.PROJECT_CREATE,
}
TEAM_PERMS = {
    Permission.TEAM_READ,
    Permission.TEAM_UPDATE,
    Permission.TEAM_DELETE,
    Permission.TEAM_MEMBER_INVITE,
    Permission.TEAM_MEMBER_REMOVE,
}
PROJECT_PERMS = {
    Permission.PROJECT_READ,
    Permission.PROJECT_UPDATE,
    Permission.PROJECT_DELETE,
    Permission.PROJECT_MEMBER_INVITE,
    Permission.PROJECT_MEMBER_REMOVE,
}
TAG_PERMS = {
    Permission.TAG_CREATE,
    Permission.TAG_READ,
    Permission.TAG_UPDATE,
    Permission.TAG_DELETE,
}
NOTEBOOK_PERMS = {
    Permission.NOTEBOOK_CREATE,
    Permission.NOTEBOOK_READ,
    Permission.NOTEBOOK_UPDATE,
    Permission.NOTEBOOK_DELETE,
}


def test_owner_is_admin_plus_delete() -> None:
    """owner = everything admin gets, plus org.delete."""
    assert ROLE_PERMISSIONS[Role.ORG_OWNER] == (
        ROLE_PERMISSIONS[Role.ORG_ADMIN] | {Permission.ORG_DELETE}
    )


def test_admin_gets_all_org_permissions_except_delete() -> None:
    assert ORG_PERMS - {Permission.ORG_DELETE} <= ROLE_PERMISSIONS[Role.ORG_ADMIN]
    assert Permission.ORG_DELETE not in ROLE_PERMISSIONS[Role.ORG_ADMIN]


def test_admin_gets_full_team_project_and_tag_access() -> None:
    """Admin universal access flows through the matrix."""
    assert TEAM_PERMS <= ROLE_PERMISSIONS[Role.ORG_ADMIN]
    assert PROJECT_PERMS <= ROLE_PERMISSIONS[Role.ORG_ADMIN]
    assert TAG_PERMS <= ROLE_PERMISSIONS[Role.ORG_ADMIN]
    assert NOTEBOOK_PERMS <= ROLE_PERMISSIONS[Role.ORG_ADMIN]


def test_member_gets_narrow_org_permissions_only() -> None:
    assert ROLE_PERMISSIONS[Role.ORG_MEMBER] == frozenset(
        {
            Permission.ORG_READ,
            Permission.MEMBER_LIST,
            Permission.TEAM_CREATE,
            Permission.PROJECT_CREATE,
        }
    )


def test_team_manager_is_implied_editor_on_team_projects() -> None:
    assert TEAM_PERMS <= ROLE_PERMISSIONS[Role.TEAM_MANAGER]
    assert PROJECT_PERMS <= ROLE_PERMISSIONS[Role.TEAM_MANAGER]
    assert TAG_PERMS <= ROLE_PERMISSIONS[Role.TEAM_MANAGER]
    assert NOTEBOOK_PERMS <= ROLE_PERMISSIONS[Role.TEAM_MANAGER]


def test_team_member_is_implied_viewer_on_team_projects() -> None:
    assert ROLE_PERMISSIONS[Role.TEAM_MEMBER] == frozenset(
        {
            Permission.TEAM_READ,
            Permission.PROJECT_READ,
            Permission.TAG_READ,
            Permission.NOTEBOOK_READ,
            Permission.SOURCE_READ,
            Permission.SEARCH_TEXT,
            Permission.SEARCH_VECTOR,
            Permission.NOTE_READ,
            Permission.COMPETITOR_READ,
            Permission.LOCATION_READ,
            Permission.SERVICE_READ,
            Permission.OBSERVATION_READ,
        }
    )


def test_project_editor_gets_all_project_and_tag_permissions() -> None:
    assert PROJECT_PERMS <= ROLE_PERMISSIONS[Role.PROJECT_EDITOR]
    assert TAG_PERMS <= ROLE_PERMISSIONS[Role.PROJECT_EDITOR]
    assert NOTEBOOK_PERMS <= ROLE_PERMISSIONS[Role.PROJECT_EDITOR]


def test_project_viewer_reads_but_never_mutates() -> None:
    assert ROLE_PERMISSIONS[Role.PROJECT_VIEWER] == frozenset(
        {
            Permission.PROJECT_READ,
            Permission.TAG_READ,
            Permission.NOTEBOOK_READ,
            Permission.SOURCE_READ,
            Permission.SEARCH_TEXT,
            Permission.SEARCH_VECTOR,
            Permission.NOTE_READ,
            Permission.COMPETITOR_READ,
            Permission.LOCATION_READ,
            Permission.SERVICE_READ,
            Permission.OBSERVATION_READ,
        }
    )
    assert Permission.TAG_CREATE not in ROLE_PERMISSIONS[Role.PROJECT_VIEWER]
    assert Permission.TAG_UPDATE not in ROLE_PERMISSIONS[Role.PROJECT_VIEWER]
    assert Permission.TAG_DELETE not in ROLE_PERMISSIONS[Role.PROJECT_VIEWER]
    assert Permission.NOTEBOOK_CREATE not in ROLE_PERMISSIONS[Role.PROJECT_VIEWER]
    assert Permission.NOTEBOOK_UPDATE not in ROLE_PERMISSIONS[Role.PROJECT_VIEWER]
    assert Permission.NOTEBOOK_DELETE not in ROLE_PERMISSIONS[Role.PROJECT_VIEWER]


def test_resolution_order_is_most_specific_scope_wins() -> None:
    """Explicit project role → team-derived role → organization role."""
    assert resolve_role(org_role="owner") == Role.ORG_OWNER
    assert resolve_role(org_role="member", team_role="manager") == Role.TEAM_MANAGER
    assert (
        resolve_role(org_role="admin", team_role="member", project_role="viewer")
        == Role.PROJECT_VIEWER
    )
    # A project role beats an org owner: deterministic strict ordering.
    assert resolve_role(org_role="owner", project_role="viewer") == Role.PROJECT_VIEWER
    assert resolve_role(org_role=None) is None
    # Pure mapping knows nothing of membership: the org-membership gate
    # lives in AuthorizationService.require, which runs before this.
    assert resolve_role(org_role=None, team_role="member") == Role.TEAM_MEMBER


def test_every_catalogued_permission_is_granted_to_some_role() -> None:
    """The catalog documents the whole surface: nothing is ungrantable."""
    granted = frozenset().union(*ROLE_PERMISSIONS.values())
    assert ALL_PERMISSIONS <= granted


# --- member.change_role ownership gate -------------------------------------


@pytest.mark.parametrize("actor", ["member", "admin", "owner"])
@pytest.mark.parametrize("target", ["member", "admin", "owner"])
def test_change_role_gate(actor: str, target: str) -> None:
    expected = {
        ("member", "member"): False,
        ("member", "admin"): False,
        ("member", "owner"): False,
        ("admin", "member"): True,
        ("admin", "admin"): False,
        ("admin", "owner"): False,
        ("owner", "member"): True,
        ("owner", "admin"): True,
        ("owner", "owner"): True,
    }[(actor, target)]
    assert can_change_role(actor_org_role=actor, target_org_role=target) is expected


# --- holds() -----------------------------------------------------------------


def test_holds_without_role_is_denied() -> None:
    assert holds(None, Permission.ORG_READ) is False
    assert holds(None, Permission.TAG_DELETE) is False


def test_holds_looks_up_the_matrix() -> None:
    assert holds(Role.ORG_OWNER, Permission.ORG_DELETE) is True
    assert holds(Role.ORG_ADMIN, Permission.ORG_DELETE) is False
    assert holds(Role.PROJECT_VIEWER, Permission.TAG_READ) is True
    assert holds(Role.PROJECT_VIEWER, Permission.TAG_DELETE) is False


# --- AuthorizationService against an in-memory unit (resolution at scope) ----


class FakeMemberships:
    def __init__(self, role: str | None) -> None:
        self.role = role
        from modules.platform.domain.entities import Membership

        self._membership = (
            Membership(organization_id=ORG_ID, app_user_id=USER_ID, role=role)
            if role
            else None
        )

    async def get(self, organization_id, app_user_id):
        return self._membership

    async def count_role(self, organization_id, role):
        return 0


class FakeTeamMemberships:
    def __init__(self, role: str | None) -> None:
        from modules.platform.domain.entities import TeamMembership

        self._membership = (
            TeamMembership(team_id=TEAM_ID, app_user_id=USER_ID, role=role)
            if role
            else None
        )

    async def get(self, team_id, app_user_id):
        return self._membership


class FakeProjectMemberships:
    def __init__(self, role: str | None) -> None:
        from modules.platform.domain.entities import ProjectMembership

        self._membership = (
            ProjectMembership(project_id=PROJECT_ID, app_user_id=USER_ID, role=role)
            if role
            else None
        )

    async def get(self, project_id, app_user_id):
        return self._membership


class FakeUnit:
    """Only what AuthorizationService touches."""

    def __init__(
        self,
        *,
        org_role: str | None,
        team_role: str | None = None,
        project_role: str | None = None,
    ) -> None:
        self.memberships = FakeMemberships(org_role)
        self.team_memberships = FakeTeamMemberships(team_role)
        self.project_memberships = FakeProjectMemberships(project_role)


ORG_ID = uuid4()
TEAM_ID = uuid4()
PROJECT_ID = uuid4()
USER_ID = uuid4()
PRINCIPAL = Principal(
    provider="test",
    subject=str(USER_ID),
    app_user_id=USER_ID,
    email="user@example.com",
    email_confirmed=True,
)


def make_authz(**roles):
    from modules.platform.application.services.authorization import (
        AuthorizationService,
    )

    return AuthorizationService(FakeUnit(**roles))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_non_member_gets_not_found_not_forbidden() -> None:
    """Guessed IDs return nothing: no membership → 404-shaped error."""
    from modules.platform.application.errors import NotFoundError

    authz = make_authz(org_role=None)
    with pytest.raises(NotFoundError):
        await authz.require(
            PRINCIPAL,
            Permission.PROJECT_READ,
            organization_id=ORG_ID,
            project_id=PROJECT_ID,
        )


@pytest.mark.asyncio
async def test_org_member_without_project_access_is_forbidden() -> None:
    from modules.platform.application.errors import ForbiddenError

    authz = make_authz(org_role="member")
    with pytest.raises(ForbiddenError):
        await authz.require(
            PRINCIPAL,
            Permission.PROJECT_READ,
            organization_id=ORG_ID,
            project_id=PROJECT_ID,
        )


@pytest.mark.asyncio
async def test_team_derived_access_comes_from_membership_not_grants() -> None:
    """Team manager/member reach team projects with no project_members row."""
    manager = make_authz(org_role="member", team_role="manager")
    assert (
        await manager.require(
            PRINCIPAL,
            Permission.TAG_UPDATE,
            organization_id=ORG_ID,
            team_id=TEAM_ID,
            project_id=PROJECT_ID,
        )
        == Role.TEAM_MANAGER
    )

    member = make_authz(org_role="member", team_role="member")
    assert (
        await member.require(
            PRINCIPAL,
            Permission.PROJECT_READ,
            organization_id=ORG_ID,
            team_id=TEAM_ID,
            project_id=PROJECT_ID,
        )
        == Role.TEAM_MEMBER
    )
    from modules.platform.application.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        await member.require(
            PRINCIPAL,
            Permission.TAG_UPDATE,
            organization_id=ORG_ID,
            team_id=TEAM_ID,
            project_id=PROJECT_ID,
        )


@pytest.mark.asyncio
async def test_explicit_project_role_beats_team_and_org_roles() -> None:
    authz = make_authz(org_role="owner", team_role="manager", project_role="viewer")
    assert (
        await authz.require(
            PRINCIPAL,
            Permission.PROJECT_READ,
            organization_id=ORG_ID,
            team_id=TEAM_ID,
            project_id=PROJECT_ID,
        )
        == Role.PROJECT_VIEWER
    )
