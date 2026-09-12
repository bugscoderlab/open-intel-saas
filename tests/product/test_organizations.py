"""HTTP seam: Organizations + memberships (ticket #5).

Covers creation (owner + audit + outbox in one transaction), permission
denials per role, the owner-only gates, immediate revocation on member
removal, and audit completeness — against the managed project.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("org-owner")


@pytest_asyncio.fixture
async def org(api, owner: TestUser, settings) -> AsyncIterator[str]:
    """An organization owned by `owner`; deleted at teardown."""
    response = await api.post(
        "/organizations",
        json={"name": f"Org {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    org_id = response.json()["id"]
    yield org_id
    # Teardown: user_factory deletes users but organizations survive their
    # creator (set-null FK), so delete the tenant row explicitly.
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "delete from public.organizations where id = $1::uuid", org_id
        )
    finally:
        await conn.close()


async def test_create_organization_makes_creator_owner(api, owner: TestUser, org: str) -> None:
    members = await api.get(
        f"/organizations/{org}/members", headers=auth_headers(owner)
    )
    assert members.status_code == 200
    rows = members.json()
    assert len(rows) == 1
    assert rows[0]["role"] == "owner"


async def test_organization_created_writes_audit_and_outbox(
    api, owner: TestUser, org: str, settings
) -> None:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        audit = await conn.fetch(
            "select * from public.audit_log where organization_id = $1::uuid"
            " and action = 'organization.create'", org,
        )
        assert len(audit) == 1
        assert audit[0]["actor_id"] == uuid.UUID(
            (await api.get("/me", headers=auth_headers(owner))).json()["app_user_id"]
        )
        outbox = await conn.fetch(
            "select * from public.outbox_events where"
            " payload ->> 'organization_id' = $1 and published_at is null", org,
        )
        assert len(outbox) == 1
        assert outbox[0]["event_type"] == "OrganizationCreated"
        assert outbox[0]["occurred_at"] is not None
    finally:
        await conn.close()


async def test_reads_write_no_audit(api, owner: TestUser, org: str, settings) -> None:
    await api.get(f"/organizations/{org}", headers=auth_headers(owner))
    await api.get(f"/organizations/{org}/members", headers=auth_headers(owner))
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        count = await conn.fetchval(
            "select count(*) from public.audit_log where organization_id = $1::uuid",
            org,
        )
        assert count == 1  # only the organization.create entry
    finally:
        await conn.close()


async def test_org_read_update_for_member(api, owner: TestUser, org: str, user_factory) -> None:
    member = await user_factory("plain-member")
    # Invite + accept so `member` joins as member.
    token = await _invite_and_accept(api, owner, org, member)
    del token
    response = await api.get(f"/organizations/{org}", headers=auth_headers(member))
    assert response.status_code == 200
    # Members cannot update.
    response = await api.patch(
        f"/organizations/{org}", json={"name": "nope"},
        headers=auth_headers(member),
    )
    assert response.status_code == 403


async def test_org_delete_is_owner_only(api, owner: TestUser, org: str, user_factory) -> None:
    admin = await user_factory("future-admin")
    await _invite_and_accept(api, owner, org, admin)
    await _change_role(api, owner, org, admin, "admin")

    response = await api.delete(f"/organizations/{org}", headers=auth_headers(admin))
    assert response.status_code == 403

    # The organization still exists for the owner.
    assert (await api.get(f"/organizations/{org}", headers=auth_headers(owner))).status_code == 200


async def test_member_change_role_owner_gates(api, owner: TestUser, org: str, user_factory) -> None:
    admin = await user_factory("role-admin")
    plain = await user_factory("role-member")
    await _invite_and_accept(api, owner, org, admin)
    await _invite_and_accept(api, owner, org, plain)
    await _change_role(api, owner, org, admin, "admin")

    admin_id = (await api.get("/me", headers=auth_headers(admin))).json()["app_user_id"]
    plain_id = (await api.get("/me", headers=auth_headers(plain))).json()["app_user_id"]

    # Admin can promote a member to admin.
    assert (await api.patch(
        f"/organizations/{org}/members/{plain_id}", json={"role": "admin"},
        headers=auth_headers(admin),
    )).status_code == 200

    # Admin cannot demote an admin (owner gate).
    assert (await api.patch(
        f"/organizations/{org}/members/{plain_id}", json={"role": "member"},
        headers=auth_headers(admin),
    )).status_code == 403

    # Owner can demote an admin.
    assert (await api.patch(
        f"/organizations/{org}/members/{plain_id}", json={"role": "member"},
        headers=auth_headers(owner),
    )).status_code == 200

    # Admin cannot touch the owner.
    owner_id = (await api.get("/me", headers=auth_headers(owner))).json()["app_user_id"]
    assert (await api.patch(
        f"/organizations/{org}/members/{owner_id}", json={"role": "member"},
        headers=auth_headers(admin),
    )).status_code == 403
    del admin_id


async def test_member_removal_revokes_access_immediately(
    api, owner: TestUser, org: str, user_factory
) -> None:
    member = await user_factory("removed-member")
    await _invite_and_accept(api, owner, org, member)
    member_id = (await api.get("/me", headers=auth_headers(member))).json()["app_user_id"]

    response = await api.delete(
        f"/organizations/{org}/members/{member_id}", headers=auth_headers(owner)
    )
    assert response.status_code == 204

    # Same token, immediately after: access is gone (no token expiry wait).
    response = await api.get(f"/organizations/{org}", headers=auth_headers(member))
    assert response.status_code == 404


async def test_member_list_is_org_wide(api, owner: TestUser, org: str, user_factory) -> None:
    other = await user_factory("listed-member")
    await _invite_and_accept(api, owner, org, other)
    members = await api.get(
        f"/organizations/{org}/members", headers=auth_headers(owner)
    )
    emails = {m["email"] for m in members.json()}
    assert owner.email in emails
    assert other.email in emails


async def test_last_owner_cannot_be_removed(
    api, owner: TestUser, org: str
) -> None:
    owner_id = (await api.get("/me", headers=auth_headers(owner))).json()["app_user_id"]
    response = await api.delete(
        f"/organizations/{org}/members/{owner_id}", headers=auth_headers(owner)
    )
    assert response.status_code in (403, 409)


# --- helpers -----------------------------------------------------------------


async def _invite_and_accept(api, owner: TestUser, org: str, invitee: TestUser) -> str:
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={"email": invitee.email, "scope": "organization", "role": "member"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    email = api.app.state.recording_email.sent[-1]
    assert email["to_email"] == invitee.email
    assert "http://shell.test/invitations/accept?token=" in email["accept_url"]
    token = email["accept_url"].rsplit("token=", 1)[1]

    response = await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )
    assert response.status_code == 204, response.text
    return token


async def _change_role(api, actor: TestUser, org: str, target: TestUser, role: str) -> None:
    target_id = (await api.get("/me", headers=auth_headers(target))).json()["app_user_id"]
    response = await api.patch(
        f"/organizations/{org}/members/{target_id}", json={"role": role},
        headers=auth_headers(actor),
    )
    assert response.status_code == 200, response.text
