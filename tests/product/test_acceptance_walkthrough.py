"""Acceptance walkthrough: register → org → invite → accept → team →
member → team project → tags → isolation (ticket #9 §18).

One journey through the whole slice with fresh users, asserting the
exact behavior the product spec promises end users.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers


@pytest_asyncio.fixture
async def walkthrough_users(user_factory) -> dict[str, TestUser]:
    return {
        "founder": await user_factory(),
        "invitee": await user_factory(),
    }


async def test_register_create_invite_accept_team_project_tags_isolation(
    api, user_factory, walkthrough_users
) -> None:
    founder = walkthrough_users["founder"]
    invitee = walkthrough_users["invitee"]
    outsider = await user_factory()

    # 1. Register, then create the Organization: the creator is owner.
    created = await api.post(
        "/organizations", json={"name": "Walkthrough Org"},
        headers=auth_headers(founder),
    )
    assert created.status_code == 201, created.text
    orgs = (await api.get(
        "/organizations", headers=auth_headers(founder)
    )).json()
    assert len(orgs) == 1
    org_id = orgs[0]["id"]

    # The creator is owner (visible in the member list).
    members = (await api.get(
        f"/organizations/{org_id}/members", headers=auth_headers(founder)
    )).json()
    assert members[0]["role"] == "owner"

    # 2. Invite.
    invite = (await api.post(
        f"/organizations/{org_id}/invitations",
        json={"email": invitee.email, "scope": "organization", "role": "member"},
        headers=auth_headers(founder),
    ))
    assert invite.status_code == 201, invite.text
    token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit(
        "token=", 1
    )[1]

    # 3. Accept.
    accepted = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )
    assert accepted.status_code == 204, accepted.text
    invitee_orgs = (await api.get(
        "/organizations", headers=auth_headers(invitee)
    )).json()
    assert [o["id"] for o in invitee_orgs] == [org_id]

    # 4. Team; the invitee joins it through a team-scoped invitation.
    team = (await api.post(
        f"/organizations/{org_id}/teams",
        json={"name": "Research"},
        headers=auth_headers(founder),
    ))
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    team_invite = (await api.post(
        f"/organizations/{org_id}/invitations",
        json={
            "email": invitee.email, "scope": "team",
            "role": "member", "team_id": team_id,
        },
        headers=auth_headers(founder),
    ))
    assert team_invite.status_code == 201, team_invite.text
    team_token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit(
        "token=", 1
    )[1]
    assert (await api.post(
        "/invitations/accept", json={"token": team_token},
        headers=auth_headers(invitee),
    )).status_code == 204
    team_members = (await api.get(
        f"/teams/{team_id}/members", headers=auth_headers(founder)
    )).json()
    assert any(
        m["app_user_id"] == invitee.auth_user_id for m in team_members
    )

    # 5. Team project (org-owned projects carry owning_team_id; the
    #    team project is what the matrix governs).
    project = (await api.post(
        f"/organizations/{org_id}/projects",
        json={
            "name": "Competitors",
            "owning_team_id": team_id,
            "visibility": "team",
        },
        headers=auth_headers(founder),
    ))
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    # 6. Tags on the project.
    for name in ("competitors", "pricing"):
        created = await api.post(
            f"/projects/{project_id}/tags",
            json={"name": name},
            headers=auth_headers(founder),
        )
        assert created.status_code == 201, created.text

    # 7. Both members see the tags; the outsider cannot even retrieve
    #    the project.
    for user in (founder, invitee):
        tags = (await api.get(
            f"/projects/{project_id}/tags", headers=auth_headers(user)
        )).json()
        assert {t["name"] for t in tags} == {"competitors", "pricing"}
    assert (await api.get(
        f"/projects/{project_id}", headers=auth_headers(outsider)
    )).status_code == 404
    assert (await api.get(
        f"/projects/{project_id}/tags", headers=auth_headers(outsider)
    )).status_code == 404

    # 8. The invitee is an org member but only a team viewer: they read
    #    the project but cannot mutate tags.
    assert (await api.post(
        f"/projects/{project_id}/tags",
        json={"name": "nope"},
        headers=auth_headers(invitee),
    )).status_code == 403
