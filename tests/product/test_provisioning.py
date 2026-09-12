"""Database seam: Application user provisioning triggers (ticket #2/#11).

Fixtures are inserted directly into ``auth.users`` / ``auth.identities``
inside rolled-back transactions (pgTAP style) against the managed Supabase
project — the same code path ``auth.admin.create_user`` and every signup
route run through. One provisioning code path, proven here.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.platform.infrastructure.settings import Settings

EMAIL_DOMAIN = "provisioning-test.open-intel.dev"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@{EMAIL_DOMAIN}"


@pytest_asyncio.fixture
async def db_conn() -> AsyncIterator[asyncpg.Connection]:
    """A direct postgres connection to the managed project (per test: each
    test runs on its own event loop, and asyncpg binds to one loop)."""
    settings = Settings.from_env()
    if not settings.database_dsn_asyncpg:
        pytest.skip("Supabase database credentials not configured")
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def tx(db_conn: asyncpg.Connection) -> AsyncIterator[asyncpg.Connection]:
    """A rolled-back transaction: fixtures never survive the test."""
    async with db_conn.transaction():
        yield db_conn


async def insert_auth_user(
    conn: asyncpg.Connection,
    email: str,
    *,
    confirmed: bool = False,
) -> uuid.UUID:
    """Insert an auth.users row the way GoTrue would for a password signup."""
    user_id = uuid.uuid4()
    confirmed_at = datetime(2026, 1, 1, tzinfo=timezone.utc) if confirmed else None
    await conn.execute(
        "insert into auth.users (id, aud, role, email, email_confirmed_at,"
        " created_at, updated_at) values ($1, 'authenticated', 'authenticated',"
        " $2, $3, now(), now())",
        user_id,
        email,
        confirmed_at,
    )
    return user_id


async def insert_identity(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    provider: str,
    provider_subject: str,
    email: str,
) -> None:
    """Insert an auth.identities row the way GoTrue does for every signup."""
    await conn.execute(
        "insert into auth.identities (provider_id, user_id, identity_data,"
        " provider, created_at, updated_at) values ($1, $2, $3::jsonb, $4, now(), now())",
        provider_subject,
        user_id,
        json.dumps({"sub": provider_subject, "email": email}),
        provider,
    )


async def get_app_user(conn: asyncpg.Connection, email: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "select * from public.app_users where lower(email) = lower($1)", email
    )


async def test_email_signup_provisions_one_application_user(
    tx: asyncpg.Connection,
) -> None:
    """Email signup: one Application user (pending) plus the email identity."""
    email = unique_email("email")
    user_id = await insert_auth_user(tx, email)
    await insert_identity(tx, user_id, "email", email, email)

    app_user = await get_app_user(tx, email)
    assert app_user is not None, "app_users row missing"
    assert app_user["status"] == "pending"
    identities = await tx.fetch(
        "select * from public.user_identities where app_user_id = $1",
        app_user["id"],
    )
    assert len(identities) == 1
    assert identities[0]["provider"] == "email"
    assert identities[0]["provider_subject"] == email
    assert identities[0]["auth_user_id"] == user_id


async def test_oauth_insert_ordering_still_records_identity(
    tx: asyncpg.Connection,
) -> None:
    """auth.users lands before auth.identities for OAuth; the identities
    trigger must link the identity the users trigger could not see."""
    email = unique_email("oauth")
    user_id = await insert_auth_user(tx, email, confirmed=True)
    # Application user already exists from the users trigger.
    assert await get_app_user(tx, email) is not None
    google_subject = f"google-sub-{uuid.uuid4().hex[:12]}"
    await insert_identity(tx, user_id, "google", google_subject, email)

    app_user = await get_app_user(tx, email)
    identities = await tx.fetch(
        "select * from public.user_identities where app_user_id = $1",
        app_user["id"],
    )
    assert len(identities) == 1
    assert identities[0]["provider"] == "google"
    assert identities[0]["provider_subject"] == google_subject
    assert identities[0]["auth_user_id"] == user_id


async def test_repeated_signups_create_no_duplicates(tx: asyncpg.Connection) -> None:
    """One person, two providers: re-running the provisioning upserts must
    not duplicate the Application user (insert-only + ON CONFLICT)."""
    email = unique_email("retry")
    user_id = await insert_auth_user(tx, email, confirmed=True)
    await insert_identity(tx, user_id, "email", email, email)
    first = await get_app_user(tx, email)
    assert first is not None

    # The same person signs in with Google afterwards. The identities
    # trigger upserts app_users again — the ON CONFLICT must keep one row.
    google_subject = f"google-sub-{uuid.uuid4().hex[:12]}"
    await insert_identity(tx, user_id, "google", google_subject, email)

    rows = await tx.fetch(
        "select * from public.app_users where lower(email) = lower($1)", email
    )
    assert len(rows) == 1, "duplicate Application user created"
    identities = await tx.fetch(
        "select * from public.user_identities where app_user_id = $1 order by provider",
        first["id"],
    )
    assert [i["provider"] for i in identities] == ["email", "google"]
    assert identities[1]["provider_subject"] == google_subject
    assert identities[1]["auth_user_id"] == user_id


async def test_email_confirmation_flips_status_to_active(
    tx: asyncpg.Connection,
) -> None:
    email = unique_email("confirm")
    user_id = await insert_auth_user(tx, email)
    await insert_identity(tx, user_id, "email", email, email)
    assert (await get_app_user(tx, email))["status"] == "pending"

    await tx.execute(
        "update auth.users set email_confirmed_at = now() where id = $1", user_id
    )

    assert (await get_app_user(tx, email))["status"] == "active"


async def test_confirmed_signup_is_active_immediately(tx: asyncpg.Connection) -> None:
    email = unique_email("preconfirmed")
    user_id = await insert_auth_user(tx, email, confirmed=True)
    await insert_identity(tx, user_id, "email", email, email)
    assert (await get_app_user(tx, email))["status"] == "active"


async def test_auth_user_deletion_removes_application_user(
    tx: asyncpg.Connection,
) -> None:
    email = unique_email("delete")
    user_id = await insert_auth_user(tx, email, confirmed=True)
    await insert_identity(tx, user_id, "email", email, email)
    assert await get_app_user(tx, email) is not None

    await tx.execute("delete from auth.users where id = $1", user_id)

    assert await get_app_user(tx, email) is None
    leftovers = await tx.fetch(
        "select * from public.user_identities where auth_user_id = $1", user_id
    )
    assert len(leftovers) == 0


async def test_admin_created_user_routes_through_same_triggers(
    db_conn: asyncpg.Connection,
) -> None:
    """auth.admin.create_user (the seed/test path) provisions an Application
    user through the same trigger functions — one provisioning code path.
    This is the one test that commits; it cleans up after itself."""
    import httpx

    settings = Settings.from_env()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        pytest.skip("Supabase admin credentials not configured")
    email = unique_email("admin-created")
    user_id = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.supabase_url}/auth/v1/admin/users",
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                },
                json={
                    "email": email,
                    "password": "test-only-password-123",
                    "email_confirm": True,
                },
            )
            assert response.status_code in (200, 201), response.text
            user_id = response.json()["id"]

        app_user = await get_app_user(db_conn, email)
        assert app_user is not None, "admin-created user was not provisioned"
        assert app_user["status"] == "active"
        identity = await db_conn.fetchrow(
            "select * from public.user_identities where app_user_id = $1",
            app_user["id"],
        )
        assert identity is not None
        assert identity["provider"] == "email"
        assert identity["auth_user_id"] == uuid.UUID(user_id)
    finally:
        if user_id:
            await db_conn.execute("delete from auth.users where id = $1::uuid", user_id)
        else:
            await db_conn.execute("delete from auth.users where email = $1", email)
    assert await get_app_user(db_conn, email) is None


async def test_trigger_functions_are_locked_down(tx: asyncpg.Connection) -> None:
    """Security definer + empty search_path + no EXECUTE for API roles."""
    functions = [
        "provision_app_user_from_auth_user",
        "provision_app_user_from_auth_identity",
        "sync_app_user_on_email_confirmation",
        "remove_app_user_on_auth_user_delete",
    ]
    for name in functions:
        row = await tx.fetchrow(
            "select prosecdef, proconfig from pg_proc p join pg_namespace n"
            " on p.pronamespace = n.oid where n.nspname = 'public' and p.proname = $1",
            name,
        )
        assert row is not None, f"{name} missing"
        assert row["prosecdef"] is True, f"{name} is not security definer"
        config = row["proconfig"] or []
        assert any(c.startswith("search_path=") for c in config), (
            f"{name} has no explicit search_path"
        )
        acl = await tx.fetchval(
            "select proacl from pg_proc p join pg_namespace n"
            " on p.pronamespace = n.oid where n.nspname = 'public' and p.proname = $1",
            name,
        )
        acl_str = str(acl or "")
        for role in ("anon", "authenticated"):
            assert f"{role}=X" not in acl_str, f"{name} granted to {role}"
