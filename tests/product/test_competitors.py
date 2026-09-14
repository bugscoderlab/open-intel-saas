"""HTTP seam: competitor directory (ticket #33, spec #31, Phase 3 1/3).

Competitor + Location CRUD through the new competitor_intelligence
module: scope derived from the project/competitor rows, the matrix
behind every authorization decision, control characters stripped before
persistence, and the module's routers absent when the module is disabled
(plan §20).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit
from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("competitor-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("competitor-viewer")


async def _invite_project_viewer(
    api, inviter: TestUser, org: str, invitee: TestUser, project_id: str
) -> None:
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={
            "email": invitee.email,
            "scope": "project",
            "role": "viewer",
            "project_id": project_id,
        },
        headers=auth_headers(inviter),
    )
    assert response.status_code == 201, response.text
    token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit("token=", 1)[1]
    accepted = await api.post(
        "/invitations/accept", json={"token": token}, headers=auth_headers(invitee)
    )
    assert accepted.status_code == 204


async def _create_competitor(api, user: TestUser, project_id: str, **body):
    return await api.post(
        f"/projects/{project_id}/competitors",
        json=body,
        headers=auth_headers(user),
    )


async def test_competitor_and_location_crud_lifecycle(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)

    created = await _create_competitor(
        api, owner, project_id, name="Paw Spa", website="https://pawspa.example", notes="Premium"
    )
    assert created.status_code == 201, created.text
    competitor = created.json()
    assert competitor["name"] == "Paw Spa"
    assert competitor["project_id"] == project_id
    assert competitor["organization_id"] == org
    competitor_id = competitor["id"]

    listed = await api.get(
        f"/projects/{project_id}/competitors", headers=auth_headers(owner)
    )
    assert [c["id"] for c in listed.json()] == [competitor_id]

    updated = await api.patch(
        f"/projects/{project_id}/competitors/{competitor_id}",
        json={"notes": "Premium, expanding"},
        headers=auth_headers(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Premium, expanding"
    assert updated.json()["website"] == "https://pawspa.example"

    # locations nested under the competitor
    loc = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/locations",
        json={"name": "Downtown", "address": "1 Jalan Ampang"},
        headers=auth_headers(owner),
    )
    assert loc.status_code == 201, loc.text
    location_id = loc.json()["id"]
    assert loc.json()["competitor_id"] == competitor_id

    locs = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}/locations",
        headers=auth_headers(owner),
    )
    assert [loc["id"] for loc in locs.json()] == [location_id]

    loc_updated = await api.patch(
        f"/projects/{project_id}/competitors/{competitor_id}/locations/{location_id}",
        json={"address": "2 Jalan Ampang"},
        headers=auth_headers(owner),
    )
    assert loc_updated.status_code == 200
    assert loc_updated.json()["address"] == "2 Jalan Ampang"

    # deleting the competitor cascades its locations
    deleted = await api.delete(
        f"/projects/{project_id}/competitors/{competitor_id}",
        headers=auth_headers(owner),
    )
    assert deleted.status_code == 204
    gone = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}",
        headers=auth_headers(owner),
    )
    assert gone.status_code == 404


async def test_competitors_are_isolated_between_organizations(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    created = await _create_competitor(api, owner, project_id, name="Secret Co")
    competitor_id = created.json()["id"]

    assert (
        await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}",
            headers=auth_headers(viewer),
        )
    ).status_code == 404
    assert (
        await api.patch(
            f"/projects/{project_id}/competitors/{competitor_id}",
            json={"name": "Hijack"},
            headers=auth_headers(viewer),
        )
    ).status_code == 404
    assert (
        await api.post(
            f"/projects/{project_id}/competitors/{competitor_id}/locations",
            json={"name": "Fake"},
            headers=auth_headers(viewer),
        )
    ).status_code == 404


async def test_project_viewer_reads_but_never_mutates_competitors(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    await _invite_project_viewer(api, owner, org, viewer, project_id)
    created = await _create_competitor(api, owner, project_id, name="Visible Co")
    competitor_id = created.json()["id"]

    read = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}",
        headers=auth_headers(viewer),
    )
    assert read.status_code == 200
    listed = await api.get(
        f"/projects/{project_id}/competitors", headers=auth_headers(viewer)
    )
    assert listed.status_code == 200

    assert (
        await _create_competitor(api, viewer, project_id, name="Nope")
    ).status_code == 403
    assert (
        await api.patch(
            f"/projects/{project_id}/competitors/{competitor_id}",
            json={"name": "Nope"},
            headers=auth_headers(viewer),
        )
    ).status_code == 403
    assert (
        await api.delete(
            f"/projects/{project_id}/competitors/{competitor_id}",
            headers=auth_headers(viewer),
        )
    ).status_code == 403


async def test_control_characters_are_stripped_before_persistence(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await new_project(api, owner, org)
    created = await _create_competitor(
        api, owner, project_id, name="Spa\x00\x1b[31m", notes="line1\nline2\x07"
    )
    assert created.status_code == 201, created.text
    competitor_id = created.json()["id"]

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        row = await conn.fetchrow(
            "select name, notes from competitor.competitors where id = $1::uuid",
            competitor_id,
        )
    finally:
        await conn.close()
    assert row["name"] == "Spa[31m"  # NUL and ESC removed
    assert "\x07" not in row["notes"]
    assert "\n" in row["notes"]  # printable whitespace kept

    # the API response exposes only the allowlisted fields
    fetched = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}",
        headers=auth_headers(owner),
    )
    assert set(fetched.json().keys()) == {
        "id",
        "organization_id",
        "project_id",
        "name",
        "website",
        "notes",
    }


async def test_module_disabled_routes_absent(
    settings, engine, user_factory
) -> None:
    """Plan §20: with competitor_intelligence disabled the API still
    starts and the competitor routes are not mounted."""
    from modules.competitor_intelligence.api.routers import (
        build_competitor_router,
    )
    from modules.competitor_intelligence.infrastructure.unit_of_work import (
        SqlCompetitorUnit,
    )
    from modules.platform.api.app import create_app
    from modules.platform.infrastructure.discovery import discover_modules
    from modules.platform.infrastructure.email import RecordingEmailProvider
    from modules.platform.infrastructure.identity import SupabaseIdentityProvider

    disabled = replace(settings, disabled_modules=frozenset({"competitor_intelligence"}))
    repo_root = Path(__file__).resolve().parents[2]
    app = create_app(
        config=disabled,
        registry=discover_modules(repo_root / "modules"),
        engine=engine,
        identity_provider=SupabaseIdentityProvider(
            supabase_url=disabled.supabase_url, engine=engine
        ),
        email_provider=RecordingEmailProvider(),
        unit_factory=lambda: SqlPlatformUnit(engine),
        invitation_base_url="http://shell.test",
        competitor_router=build_competitor_router(),
        competitor_unit_factory=lambda: SqlCompetitorUnit(engine),
    )
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any("competitors" in p for p in paths)
    # health still works with the module disabled
    assert "/healthz" in paths
