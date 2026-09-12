"""HTTP seam: Teams + projects + memberships (ticket #7).

Team creation makes the creator manager; team membership implies
project access through the matrix (team manager = editor, team member =
viewer) with no denormalized project grants; project creation supports
organization-owned and team-owned with visibility; project invites carry
the editor/viewer choice.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers, unique_test_email


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("tp-owner")


@pytest_asyncio.fixture
async def org(api, owner: TestUser, settings) -> str:
    response = await api.post(
        "/organizations",
        json={"name": f"Org {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    org_id = response.json()["id"]
    yield org_id
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "delete from public.organizations where id = $1::uuid", org_id
        )
    finally:
        await conn.close()


async def _join_org(api, owner: TestUser, org: str, invitee: TestUser) -> None:
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={"email": invitee.email, "scope": "organization", "role": "member"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit("token=", 1)[1]
    assert (await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )).status_code == 204


async def _invite_to(
    api, inviter: TestUser, org: str, invitee: TestUser,
    scope: str, role: str, team_id: str | None = None, project_id: str | None = None,
) -> None:
    body: dict = {"email": invitee.email, "scope": scope, "role": role}
    if team_id:
        body["team_id"] = team_id
    if project_id:
        body["project_id"] = project_id
    response = await api.post(
        f"/organizations/{org}/invitations", json=body,
        headers=auth_headers(inviter),
    )
    assert response.status_code == 201, response.text
    token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit("token=", 1)[1]
    assert (await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )).status_code == 204


async def _create_team(api, actor: TestUser, org: str, name: str | None = None) -> str:
    response = await api.post(
        f"/organizations/{org}/teams",
        json={"name": name or f"Team {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_team_creation_makes_creator_manager(api, owner: TestUser, org: str) -> None:
    team_id = await _create_team(api, owner, org)
    members = (await api.get(
        f"/teams/{team_id}/members", headers=auth_headers(owner)
    )).json()
    assert len(members) == 1
    assert members[0]["role"] == "manager"


async def test_any_member_can_create_team(
    api, owner: TestUser, org: str, user_factory
) -> None:
    member = await user_factory("tp-teamcreator")
    await _join_org(api, owner, org, member)
    assert await _create_team(api, member, org)


async def test_team_manager_invites_and_org_admin_invites(
    api, owner: TestUser, org: str, user_factory
) -> None:
    manager = await user_factory("tp-manager")
    joiner = await user_factory("tp-joiner")
    admin = await user_factory("tp-admin")
    await _join_org(api, owner, org, manager)
    await _join_org(api, owner, org, joiner)
    await _join_org(api, owner, org, admin)
    admin_id = (await api.get("/me", headers=auth_headers(admin))).json()["app_user_id"]
    await api.patch(
        f"/organizations/{org}/members/{admin_id}", json={"role": "admin"},
        headers=auth_headers(owner),
    )

    team_id = await _create_team(api, manager, org)

    # Team manager can invite to the team.
    await _invite_to(api, manager, org, joiner, "team", "member", team_id=team_id)
    members = (await api.get(
        f"/teams/{team_id}/members", headers=auth_headers(manager)
    )).json()
    assert len(members) == 2

    # A plain org member cannot invite to the team.
    stranger = await user_factory("tp-stranger")
    await _join_org(api, owner, org, stranger)
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={
            "email": unique_test_email(), "scope": "team",
            "role": "member", "team_id": team_id,
        },
        headers=auth_headers(stranger),
    )
    assert response.status_code == 403

    # But an org admin can (matrix, not a role-name check in routes).
    admin_invitee = await user_factory("tp-admin-invitee")
    await _join_org(api, owner, org, admin_invitee)
    await _invite_to(api, admin, org, admin_invitee, "team", "member", team_id=team_id)


async def test_team_manager_is_editor_team_member_is_viewer_on_team_projects(
    api, owner: TestUser, org: str, user_factory
) -> None:
    manager = await user_factory("tp-tm")
    teammate = await user_factory("tp-tmm")
    await _join_org(api, owner, org, manager)
    await _join_org(api, owner, org, teammate)
    team_id = await _create_team(api, manager, org)

    # Team-owned project created by the manager.
    response = await api.post(
        f"/organizations/{org}/projects",
        json={"name": "Team project", "owning_team_id": team_id, "visibility": "team"},
        headers=auth_headers(manager),
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]

    # Invite the teammate to the team; they get viewer access to team
    # projects with NO project_members row (matrix derivation).
    await _invite_to(api, manager, org, teammate, "team", "member", team_id=team_id)
    project_members = (await api.get(
        f"/projects/{project_id}/members", headers=auth_headers(manager)
    )).json()
    teammate_id = (await api.get("/me", headers=auth_headers(teammate))).json()["app_user_id"]
    assert all(m["app_user_id"] != teammate_id for m in project_members)

    # Team member: reads, cannot mutate.
    assert (await api.get(
        f"/projects/{project_id}", headers=auth_headers(teammate)
    )).status_code == 200
    assert (await api.patch(
        f"/projects/{project_id}", json={"name": "hijack"},
        headers=auth_headers(teammate),
    )).status_code == 403

    # Team manager: mutates.
    assert (await api.patch(
        f"/projects/{project_id}", json={"name": "Team project v2"},
        headers=auth_headers(manager),
    )).status_code == 200


async def test_project_create_requires_permission_and_valid_team(
    api, owner: TestUser, org: str, user_factory
) -> None:
    outsider = await user_factory("tp-proj-outsider")
    response = await api.post(
        f"/organizations/{org}/projects",
        json={"name": "nope"},
        headers=auth_headers(outsider),
    )
    assert response.status_code == 404

    member = await user_factory("tp-proj-member")
    await _join_org(api, owner, org, member)
    response = await api.post(
        f"/organizations/{org}/projects",
        json={"name": "Mine", "visibility": "organization"},
        headers=auth_headers(member),
    )
    assert response.status_code == 201
    assert response.json()["visibility"] == "organization"

    # Bogus visibility and cross-org team are rejected.
    assert (await api.post(
        f"/organizations/{org}/projects",
        json={"name": "bad", "visibility": "public"},
        headers=auth_headers(member),
    )).status_code == 422
    assert (await api.post(
        f"/organizations/{org}/projects",
        json={"name": "bad", "owning_team_id": str(uuid.uuid4())},
        headers=auth_headers(member),
    )).status_code == 404


async def test_project_member_invite_role_choice(
    api, owner: TestUser, org: str, user_factory
) -> None:
    editor = await user_factory("tp-editor")
    viewer = await user_factory("tp-viewer")
    outsider_editor = await user_factory("tp-outsider-editor")
    await _join_org(api, owner, org, editor)
    await _join_org(api, owner, org, viewer)
    await _join_org(api, owner, org, outsider_editor)

    response = await api.post(
        f"/organizations/{org}/projects",
        json={"name": "Collab"},
        headers=auth_headers(owner),
    )
    project_id = response.json()["id"]

    # The owner (project editor via matrix) invites with chosen roles.
    await _invite_to(api, owner, org, editor, "project", "editor", project_id=project_id)
    await _invite_to(api, owner, org, viewer, "project", "viewer", project_id=project_id)
    members = (await api.get(
        f"/projects/{project_id}/members", headers=auth_headers(owner)
    )).json()
    roles = {m["app_user_id"]: m["role"] for m in members}
    editor_id = (await api.get("/me", headers=auth_headers(editor))).json()["app_user_id"]
    viewer_id = (await api.get("/me", headers=auth_headers(viewer))).json()["app_user_id"]
    assert roles[editor_id] == "editor"
    assert roles[viewer_id] == "viewer"

    # Viewer cannot invite (project.member_invite is editor+).
    assert (await api.post(
        f"/organizations/{org}/invitations",
        json={
            "email": unique_test_email(), "scope": "project",
            "role": "viewer", "project_id": project_id,
        },
        headers=auth_headers(viewer),
    )).status_code == 403

    # Project editor can invite and remove members.
    new_member = await user_factory("tp-late")
    await _join_org(api, owner, org, new_member)
    await _invite_to(api, editor, org, new_member, "project", "viewer", project_id=project_id)
    new_id = (await api.get("/me", headers=auth_headers(new_member))).json()["app_user_id"]
    assert (await api.delete(
        f"/projects/{project_id}/members/{new_id}", headers=auth_headers(editor)
    )).status_code == 204
    del outsider_editor


async def test_team_and_project_mutations_write_audit(
    api, owner: TestUser, org: str, settings
) -> None:
    team_id = await _create_team(api, owner, org)
    await api.post(
        f"/organizations/{org}/projects",
        json={"name": "Audited", "owning_team_id": team_id},
        headers=auth_headers(owner),
    )
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        actions = [
            row["action"]
            for row in await conn.fetch(
                "select action from public.audit_log where organization_id = $1::uuid"
                " and action in ('team.create', 'project.create') order by id", org
            )
        ]
        assert actions == ["team.create", "project.create"]
    finally:
        await conn.close()
