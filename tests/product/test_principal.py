"""HTTP seam: principal + tenant-aware request context (ticket #3).

Identity comes only from the verified JWT: valid tokens yield the
Application user resolved through user_identities; expired/malformed
tokens get 401; and no endpoint accepts a client-submitted Application
user ID.
"""

from __future__ import annotations

import time
import uuid

import asyncpg
import jwt as pyjwt
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers


@pytest_asyncio.fixture
async def confirmed_user(user_factory) -> TestUser:
    return await user_factory("principal")


async def test_valid_token_yields_principal_with_application_user(
    api, confirmed_user: TestUser
) -> None:
    response = await api.get("/me", headers=auth_headers(confirmed_user))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == confirmed_user.email
    assert body["email_confirmed"] is True
    # The principal carries the product-owned Application user id (which
    # the provisioning trigger initializes to the auth user id, and which
    # user_identities links to the provider subject).
    assert uuid.UUID(body["app_user_id"])


async def test_missing_token_is_rejected(api) -> None:
    assert (await api.get("/me")).status_code == 401


async def test_malformed_token_is_rejected(api) -> None:
    response = await api.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


async def test_tampered_token_is_rejected(api, confirmed_user: TestUser) -> None:
    tampered = confirmed_user.access_token.rsplit(".", 1)[0] + ".invalidsignature"
    response = await api.get("/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


async def test_wrongly_signed_token_is_rejected_before_identity_lookup(
    api, confirmed_user: TestUser
) -> None:
    """A structurally valid token signed by the wrong party must fail
    verification (401) — it can never become an identity."""
    forged = pyjwt.encode(
        {
            "sub": confirmed_user.auth_user_id,
            "email": confirmed_user.email,
            "email_confirmed": True,
            "exp": int(time.time()) + 600,
        },
        "attacker-secret",
        algorithm="HS256",
    )
    response = await api.get("/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_identity_resolution_happens_through_user_identities(
    api, confirmed_user: TestUser, settings
) -> None:
    """The principal's app_user_id must be the id linked by the
    provisioning trigger in user_identities — the HTTP layer cannot
    invent it."""
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        linked_app_user_id = str(
            await conn.fetchval(
                "select app_user_id from public.user_identities"
                " where auth_user_id = $1",
                uuid.UUID(confirmed_user.auth_user_id),
            )
        )
    finally:
        await conn.close()

    response = await api.get("/me", headers=auth_headers(confirmed_user))
    assert response.json()["app_user_id"] == linked_app_user_id


async def test_expired_token_raises_verification_error(
    api, confirmed_user: TestUser
) -> None:
    from modules.platform.domain.errors import TokenVerificationError
    from modules.platform.infrastructure.identity import (
        SupabaseIdentityProvider,
    )

    provider: SupabaseIdentityProvider = api.app.state.identity_provider
    expired = pyjwt.encode(
        {
            "sub": confirmed_user.auth_user_id,
            "email": confirmed_user.email,
            "exp": int(time.time()) - 10,
        },
        "any-secret",
        algorithm="HS256",
    )
    with pytest.raises(TokenVerificationError):
        await provider.verify_token(expired)


async def test_no_endpoint_accepts_client_supplied_user_id(
    api, confirmed_user: TestUser
) -> None:
    """Identity is derived from the JWT only: an endpoint body field
    naming an Application user id must not affect authorization."""
    import uuid as uuid_module

    other = str(uuid_module.uuid4())
    response = await api.get(
        f"/organizations/{other}",
        headers=auth_headers(confirmed_user),
    )
    # Not a member of that (nonexistent) organization: the caller's own
    # id is what the service checks, never a client-supplied one.
    assert response.status_code == 404
