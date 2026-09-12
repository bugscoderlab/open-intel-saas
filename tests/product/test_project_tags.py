"""HTTP seam: Project tag CRUD (ticket #8) — the tenant-scoping pattern
proved end to end: every row carries organization_id + project_id,
viewers read but never mutate, and repositories enforce the scope on
every query.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("tag-owner")


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


async def _project(api, owner: TestUser, org: str) -> str:
    response = await api.post(
        f"/organizations/{org}/projects",
        json={"name": f"Project {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


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


async def _invite_project(
    api, inviter: TestUser, org: str, invitee: TestUser, project_id: str, role: str
) -> None:
    response = await api.post(
        f"/organizations/{org}/invitations",
        json={
            "email": invitee.email, "scope": "project",
            "role": role, "project_id": project_id,
        },
        headers=auth_headers(inviter),
    )
    assert response.status_code == 201, response.text
    token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit("token=", 1)[1]
    assert (await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )).status_code == 204


async def test_editor_full_crud_and_rows_carry_tenant_scope(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await _project(api, owner, org)

    created = await api.post(
        f"/projects/{project_id}/tags",
        json={"name": "pricing", "color": "#ff0000"},
        headers=auth_headers(owner),
    )
    assert created.status_code == 201, created.text
    tag = created.json()
    assert tag["organization_id"] == org
    assert tag["project_id"] == project_id

    tag_id = tag["id"]
    listed = (await api.get(
        f"/projects/{project_id}/tags", headers=auth_headers(owner)
    )).json()
    assert [t["name"] for t in listed] == ["pricing"]

    updated = await api.patch(
        f"/projects/{project_id}/tags/{tag_id}",
        json={"name": "price-watch"},
        headers=auth_headers(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "price-watch"
    assert updated.json()["color"] == "#ff0000"  # untouched field kept

    assert (await api.delete(
        f"/projects/{project_id}/tags/{tag_id}", headers=auth_headers(owner)
    )).status_code == 204
    assert (await api.get(
        f"/projects/{project_id}/tags", headers=auth_headers(owner)
    )).json() == []

    # And the physical row pattern: both tenant keys present.
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        cols = await conn.fetch(
            """
            select column_name from information_schema.columns
            where table_schema = 'public' and table_name = 'project_tags'
              and column_name in ('organization_id', 'project_id')
            """
        )
        assert {c["column_name"] for c in cols} == {"organization_id", "project_id"}
    finally:
        await conn.close()


async def test_viewer_reads_but_never_mutates(
    api, owner: TestUser, org: str, user_factory
) -> None:
    project_id = await _project(api, owner, org)
    viewer = await user_factory("tag-viewer")
    await _join_org(api, owner, org, viewer)
    await _invite_project(api, owner, org, viewer, project_id, "viewer")

    assert (await api.post(
        f"/projects/{project_id}/tags", json={"name": "nope"},
        headers=auth_headers(viewer),
    )).status_code == 403

    editor_tag = await api.post(
        f"/projects/{project_id}/tags", json={"name": "target"},
        headers=auth_headers(owner),
    )
    tag_id = editor_tag.json()["id"]
    assert (await api.patch(
        f"/projects/{project_id}/tags/{tag_id}", json={"name": "rename"},
        headers=auth_headers(viewer),
    )).status_code == 403
    assert (await api.delete(
        f"/projects/{project_id}/tags/{tag_id}", headers=auth_headers(viewer)
    )).status_code == 403
    # Reads are fine.
    assert (await api.get(
        f"/projects/{project_id}/tags", headers=auth_headers(viewer)
    )).status_code == 200


async def test_guessed_project_id_returns_nothing(
    api, owner: TestUser, org: str, user_factory
) -> None:
    """IDs are not an oracle: no membership → 404, never the tags."""
    project_id = await _project(api, owner, org)
    stranger = await user_factory("tag-stranger")
    response = await api.get(
        f"/projects/{project_id}/tags", headers=auth_headers(stranger)
    )
    assert response.status_code == 404

    ghost = str(uuid.uuid4())
    assert (await api.get(
        f"/projects/{ghost}/tags", headers=auth_headers(owner)
    )).status_code == 404


async def test_guessed_tag_id_returns_nothing(
    api, owner: TestUser, org: str, user_factory
) -> None:
    project_id = await _project(api, owner, org)
    viewer = await user_factory("tag-guesser")
    await _join_org(api, owner, org, viewer)
    await _invite_project(api, owner, org, viewer, project_id, "viewer")
    ghost = str(uuid.uuid4())
    assert (await api.patch(
        f"/projects/{project_id}/tags/{ghost}", json={"name": "x"},
        headers=auth_headers(owner),
    )).status_code == 404
    assert (await api.delete(
        f"/projects/{project_id}/tags/{ghost}", headers=auth_headers(owner)
    )).status_code == 404


async def test_client_supplied_ids_cannot_widen_scope(
    api, owner: TestUser, org: str
) -> None:
    """A body carrying another project_id/organization_id changes nothing:
    the URL project is the scope, derived server-side from the row."""
    project_id = await _project(api, owner, org)
    other_id = await _project(api, owner, org)
    response = await api.post(
        f"/projects/{project_id}/tags",
        json={"name": "scope-test", "project_id": other_id,
              "organization_id": str(uuid.uuid4())},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    assert response.json()["project_id"] == project_id
    assert response.json()["organization_id"] == org
    # The other project has no tags.
    assert (await api.get(
        f"/projects/{other_id}/tags", headers=auth_headers(owner)
    )).json() == []


async def test_tag_writes_are_audited(api, owner: TestUser, org: str, settings) -> None:
    project_id = await _project(api, owner, org)
    tag = (await api.post(
        f"/projects/{project_id}/tags", json={"name": "audit-me"},
        headers=auth_headers(owner),
    )).json()
    await api.patch(
        f"/projects/{project_id}/tags/{tag['id']}", json={"name": "audit-me-2"},
        headers=auth_headers(owner),
    )
    await api.delete(
        f"/projects/{project_id}/tags/{tag['id']}", headers=auth_headers(owner)
    )
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        actions = [
            row["action"]
            for row in await conn.fetch(
                "select action from public.audit_log where organization_id = $1::uuid"
                " and action like 'tag.%' order by id", org
            )
        ]
        assert actions == ["tag.create", "tag.update", "tag.delete"]
    finally:
        await conn.close()
