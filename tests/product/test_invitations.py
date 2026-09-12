"""HTTP seam: Invitations (ticket #6).

Hashed single-use expiring tokens, the email-link click page preview,
the confirmed-email gate, atomic consume + membership, replay and race
protection, per-scope Permission enforcement, and audit entries.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers, unique_test_email


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("inv-owner")


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


async def _invite(
    api, inviter: TestUser, org: str, email: str,
    scope: str = "organization", role: str = "member",
    team_id: str | None = None, project_id: str | None = None,
) -> str:
    body: dict = {"email": email, "scope": scope, "role": role}
    if team_id:
        body["team_id"] = team_id
    if project_id:
        body["project_id"] = project_id
    response = await api.post(
        f"/organizations/{org}/invitations", json=body,
        headers=auth_headers(inviter),
    )
    assert response.status_code == 201, response.text
    return api.app.state.recording_email.sent[-1]["accept_url"].rsplit("token=", 1)[1]


async def test_invitation_creation_enforces_permission(
    api, owner: TestUser, org: str, user_factory
) -> None:
    outsider = await user_factory("inv-outsider")
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={"email": unique_test_email(), "scope": "organization", "role": "member"},
        headers=auth_headers(outsider),
    )
    assert response.status_code == 404  # not a member: nothing to see

    member = await user_factory("inv-member")
    token = await _invite(api, owner, org, member.email)
    await api.post("/invitations/accept", json={"token": token},
                   headers=auth_headers(member))
    # Plain members cannot invite (matrix: member.invite is owner/admin).
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={"email": unique_test_email(), "scope": "organization", "role": "member"},
        headers=auth_headers(member),
    )
    assert response.status_code == 403


async def test_invitation_never_touches_auth_users(
    api, owner: TestUser, org: str, settings
) -> None:
    email = unique_test_email("stranger")
    await _invite(api, owner, org, email)
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        row = await conn.fetchval(
            "select count(*) from auth.users where lower(email) = lower($1)", email
        )
        assert row == 0, "invite created or touched an auth user"
        # Token is stored hashed; the raw token appears only in the email.
        stored = await conn.fetchval(
            "select token_hash from public.invitations where lower(email) = lower($1)",
            email,
        )
        assert stored is not None
        sent = api.app.state.recording_email.sent[-1]["accept_url"]
        raw = sent.rsplit("token=", 1)[1]
        assert stored != raw
        import hashlib

        assert stored == hashlib.sha256(raw.encode()).hexdigest()
    finally:
        await conn.close()


async def test_invitation_email_goes_through_app_provider(
    api, owner: TestUser, org: str
) -> None:
    email = unique_test_email("delivered")
    await _invite(api, owner, org, email)
    sent = api.app.state.recording_email.sent[-1]
    assert sent["to_email"] == email
    assert sent["accept_url"].startswith("http://shell.test/invitations/accept?token=")
    # The link routes through the click page, not a raw API endpoint.
    path = urlparse(sent["accept_url"]).path
    assert path == "/invitations/accept"


async def test_preview_needs_no_session(api, owner: TestUser, org: str) -> None:
    email = unique_test_email("preview")
    token = await _invite(api, owner, org, email)
    response = await api.get(f"/invitations/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["scope"] == "organization"
    assert body["role"] == "member"


async def test_preview_of_unknown_or_consumed_token_is_indistinguishable(
    api, owner: TestUser, org: str, user_factory
) -> None:
    invitee = await user_factory("cons-then-preview")
    token = await _invite(api, owner, org, invitee.email)
    await api.post("/invitations/accept", json={"token": token},
                   headers=auth_headers(invitee))
    assert (await api.get(f"/invitations/{token}")).status_code == 410
    assert (await api.get(f"/invitations/{uuid.uuid4().hex * 2}")).status_code == 410


async def test_accept_with_matching_confirmed_email_joins(
    api, owner: TestUser, org: str, user_factory
) -> None:
    invitee = await user_factory("accept-ok")
    token = await _invite(api, owner, org, invitee.email)
    response = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )
    assert response.status_code == 204
    members = (await api.get(
        f"/organizations/{org}/members", headers=auth_headers(owner)
    )).json()
    joined = [m for m in members if m["email"] == invitee.email]
    assert len(joined) == 1 and joined[0]["role"] == "member"


async def test_accept_with_mismatched_session_email_is_rejected(
    api, owner: TestUser, org: str, user_factory
) -> None:
    email = unique_test_email("victim")
    token = await _invite(api, owner, org, email)
    attacker = await user_factory("attacker")
    response = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(attacker),
    )
    assert response.status_code == 403
    # The invitation remains usable by the real invitee afterwards.
    invitee = await user_factory("real")

    # (re-point the invitation at the real invitee's email via a fresh one)
    token2 = await _invite(api, owner, org, invitee.email)
    assert (await api.post(
        "/invitations/accept", json={"token": token2},
        headers=auth_headers(invitee),
    )).status_code == 204


async def test_consumed_token_cannot_be_replayed(
    api, owner: TestUser, org: str, user_factory
) -> None:
    invitee = await user_factory("replay")
    token = await _invite(api, owner, org, invitee.email)
    first = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )
    assert first.status_code == 204
    second = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )
    assert second.status_code == 410
    # Still exactly one membership.
    members = (await api.get(
        f"/organizations/{org}/members", headers=auth_headers(owner)
    )).json()
    assert len([m for m in members if m["email"] == invitee.email]) == 1


async def test_concurrent_accepts_race_to_a_single_winner(
    api, owner: TestUser, org: str, user_factory
) -> None:
    """Two racing accepts of the same token: one 204, one 410, one membership."""
    import asyncio

    invitee = await user_factory("race")
    token = await _invite(api, owner, org, invitee.email)

    async def attempt():
        return await api.post(
            "/invitations/accept", json={"token": token},
            headers=auth_headers(invitee),
        )

    results = await asyncio.gather(attempt(), attempt())
    statuses = sorted(r.status_code for r in results)
    assert statuses == [204, 410]
    members = (await api.get(
        f"/organizations/{org}/members", headers=auth_headers(owner)
    )).json()
    assert len([m for m in members if m["email"] == invitee.email]) == 1


async def test_invite_and_accept_write_audit_entries(
    api, owner: TestUser, org: str, user_factory, settings
) -> None:
    invitee = await user_factory("audit")
    token = await _invite(api, owner, org, invitee.email)
    await api.post("/invitations/accept", json={"token": token},
                   headers=auth_headers(invitee))
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        actions = [
            row["action"]
            for row in await conn.fetch(
                "select action from public.audit_log where organization_id = $1::uuid"
                " and action like 'invitation.%' order by id", org
            )
        ]
        assert actions == ["invitation.create", "invitation.accept"]
    finally:
        await conn.close()


async def test_expired_token_is_rejected(
    api, owner: TestUser, org: str, user_factory, settings
) -> None:
    email = unique_test_email("expired")
    token = await _invite(api, owner, org, email)
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "update public.invitations set expires_at = now() - interval '1 second'"
            " where email = $1", email
        )
    finally:
        await conn.close()
    ghost = await user_factory("expired-accept")
    # Expiry is checked before the email match: any confirmed session
    # gets the same indistinguishable 410.
    response = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(ghost),
    )
    assert response.status_code == 410


async def test_already_member_cannot_be_reinvited(
    api, owner: TestUser, org: str, user_factory
) -> None:
    member = await user_factory("dupe")
    token = await _invite(api, owner, org, member.email)
    await api.post("/invitations/accept", json={"token": token},
                   headers=auth_headers(member))
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={"email": member.email, "scope": "organization", "role": "member"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 409
