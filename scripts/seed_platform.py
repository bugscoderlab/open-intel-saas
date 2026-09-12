"""Seed: two Organizations × two Application users each (ticket #9).

Idempotent by construction: users are reused when their email already
exists, and organizations are looked up by name before creation. Runs
against the managed Supabase project from the repository root:

    uv run python scripts/seed_platform.py
    make seed

Cross-tenant isolation is demonstrable by hand afterwards: sign in as
seed-a1 and try to reach Seed Org Beta's data (and vice versa).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import httpx
from dotenv import load_dotenv

from modules.platform.application.services import (
    invitation_service,
    organization_service,
    project_service,
    tag_service,
    team_service,
)
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.identity import Principal
from modules.platform.infrastructure.db import create_engine
from modules.platform.infrastructure.settings import Settings
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit

SEED_DOMAIN = "seed.open-intel.dev"


@dataclass(frozen=True)
class SeedUser:
    key: str
    email: str

    @property
    def principal_email(self) -> str:
        return self.email


USERS = {
    "a1": SeedUser("a1", f"seed-a1@{SEED_DOMAIN}"),
    "a2": SeedUser("a2", f"seed-a2@{SEED_DOMAIN}"),
    "b1": SeedUser("b1", f"seed-b1@{SEED_DOMAIN}"),
    "b2": SeedUser("b2", f"seed-b2@{SEED_DOMAIN}"),
}

ORG_A = "Seed Org Alpha"
ORG_B = "Seed Org Beta"
TEAM_A = "Alpha Team"
PROJECT_A = "Alpha Project"
PROJECT_B = "Beta Project"
TAGS_A = ("competitors", "pricing")


async def _ensure_user(
    settings: Settings, http: httpx.AsyncClient, password: str, user: SeedUser
) -> str:
    """Create the auth user when missing; return the Application user id."""
    import asyncpg

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        app_user_id = await conn.fetchval(
            "select id from public.app_users where lower(email) = lower($1)",
            user.email,
        )
        if app_user_id is not None:
            return str(app_user_id)
    finally:
        await conn.close()

    response = await http.post(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers={
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        },
        json={"email": user.email, "password": password, "email_confirm": True},
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"cannot create seed user {user.email}: {response.text}")

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        app_user_id = await conn.fetchval(
            "select id from public.app_users where lower(email) = lower($1)",
            user.email,
        )
    finally:
        await conn.close()
    assert app_user_id is not None, "provisioning trigger did not run"
    return str(app_user_id)


def _principal(app_user_id: str, email: str) -> Principal:
    return Principal(
        provider="seed",
        subject=app_user_id,
        app_user_id=UUID(app_user_id),
        email=email,
        email_confirmed=True,
    )


async def _ensure_organization(
    unit: SqlPlatformUnit, principal: Principal, name: str
):
    """Return the organization id, creating it (owner: principal) when the
    principal does not already belong to an organization of that name."""
    existing = await organization_service.list_organizations(unit, principal)
    for organization in existing:
        if organization.name == name:
            return organization.id
    organization = await organization_service.create_organization(
        unit, principal, name=name
    )
    return organization.id


async def _invite_and_accept(
    unit: SqlPlatformUnit,
    email_provider,
    inviter: Principal,
    invitee: Principal,
    *,
    organization_id: UUID,
    scope: str,
    role: str,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
) -> None:
    authz = AuthorizationService(unit)
    await invitation_service.create_invitation(
        unit,
        authz,
        email_provider,
        inviter,
        organization_id=organization_id,
        scope=scope,
        email=invitee.email,
        role=role,
        team_id=team_id,
        project_id=project_id,
        base_url="http://localhost:3000",
    )
    raw_token = _last_sent_token(email_provider)
    await invitation_service.accept_invitation(
        unit, invitee, raw_token=raw_token
    )


def _last_sent_token(email_provider) -> str:
    return email_provider.sent[-1]["accept_url"].rsplit("token=", 1)[1]


class _CollectingEmail:
    """Seed inviter: captures the raw token instead of sending email."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_invitation(self, **kwargs) -> None:
        self.sent.append(kwargs)


async def seed(settings: Settings) -> list[str]:
    """Run the seed; returns a human-readable summary."""
    password = settings.seed_password
    async with httpx.AsyncClient(timeout=30) as http:
        app_user_ids = {
            key: await _ensure_user(settings, http, password, user)
            for key, user in USERS.items()
        }

    engine = create_engine(settings.database_dsn)
    created: list[str] = []
    try:
        email = _CollectingEmail()
        async with SqlPlatformUnit(engine) as unit:
            a1 = _principal(app_user_ids["a1"], USERS["a1"].email)
            a2 = _principal(app_user_ids["a2"], USERS["a2"].email)
            b1 = _principal(app_user_ids["b1"], USERS["b1"].email)
            b2 = _principal(app_user_ids["b2"], USERS["b2"].email)

            org_a = await _ensure_organization(unit, a1, ORG_A)
            org_b = await _ensure_organization(unit, b1, ORG_B)

            # Memberships (idempotent: duplicate invites are refused).
            await _maybe_invite_org(unit, email, a1, a2, org_a)
            await _maybe_invite_org(unit, email, b1, b2, org_b)

            # Alpha: team + team-owned project + tags.
            authz_a = AuthorizationService(unit)
            teams = await team_service.list_teams(unit, authz_a, a1, organization_id=org_a)
            team_a = next((t for t in teams if t.name == TEAM_A), None)
            if team_a is None:
                team_a = await team_service.create_team(
                    unit, authz_a, a1, organization_id=org_a, name=TEAM_A
                )
                created.append(f"team {TEAM_A}")
            if not await unit.team_memberships.get(team_a.id, a2.app_user_id):
                await _invite_and_accept(
                    unit, email, a1, a2,
                    organization_id=org_a, scope="team", role="member",
                    team_id=team_a.id,
                )
            projects_a = await project_service.list_projects(
                unit, authz_a, a1, organization_id=org_a
            )
            project_a = next((p for p in projects_a if p.name == PROJECT_A), None)
            if project_a is None:
                project_a = await project_service.create_project(
                    unit, authz_a, a1,
                    organization_id=org_a, name=PROJECT_A,
                    owning_team_id=team_a.id, visibility="team",
                )
                created.append(f"project {PROJECT_A}")
            existing_tags = {
                t.name
                for t in await tag_service.list_tags(
                    unit, authz_a, a1, project_id=project_a.id
                )
            }
            for name in TAGS_A:
                if name not in existing_tags:
                    await tag_service.create_tag(
                        unit, authz_a, a1, project_id=project_a.id, name=name
                    )
                    created.append(f"tag {name}")

            # Beta: plain org-owned project.
            authz_b = AuthorizationService(unit)
            projects_b = await project_service.list_projects(
                unit, authz_b, b1, organization_id=org_b
            )
            if not any(p.name == PROJECT_B for p in projects_b):
                await project_service.create_project(
                    unit, authz_b, b1, organization_id=org_b, name=PROJECT_B
                )
                created.append(f"project {PROJECT_B}")

            await unit.commit()
    finally:
        await engine.dispose()

    return created


async def _maybe_invite_org(
    unit: SqlPlatformUnit,
    email: _CollectingEmail,
    inviter: Principal,
    invitee: Principal,
    organization_id: UUID,
) -> None:
    if await unit.memberships.get(organization_id, invitee.app_user_id):
        return
    await _invite_and_accept(
        unit, email, inviter, invitee,
        organization_id=organization_id, scope="organization", role="member",
    )


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    if not settings.database_dsn:
        raise SystemExit("SUPABASE_DB_HOST / SUPABASE_DB_PASSWORD not configured")
    created = await seed(settings)
    if created:
        print("seeded: " + ", ".join(created))
    else:
        print("seed data already present — nothing to do")
    print(f"  users: {', '.join(u.email for u in USERS.values())}")
    print(f"  password: {settings.seed_password}")


if __name__ == "__main__":
    asyncio.run(main())
