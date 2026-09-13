"""HTTP seam: Notebook CRUD (ticket #22, spec #21) — the research module's
first vertical, copying the Project tag tenant-scoping pattern end to end:
every row carries organization_id + project_id, viewers read but never
mutate, and repositories enforce the scope on every query.
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
    return await user_factory("notebook-owner")


@pytest_asyncio.fixture
async def org(api, owner: TestUser, settings) -> AsyncIterator[str]:
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
        f"/projects/{project_id}/notebooks",
        json={"name": "Market scan", "description": "Q3 competitors"},
        headers=auth_headers(owner),
    )
    assert created.status_code == 201, created.text
    notebook = created.json()
    assert notebook["organization_id"] == org
    assert notebook["project_id"] == project_id
    assert notebook["archived"] is False
    notebook_id = notebook["id"]

    listed = (await api.get(
        f"/projects/{project_id}/notebooks", headers=auth_headers(owner)
    )).json()
    assert [n["name"] for n in listed] == ["Market scan"]

    updated = await api.patch(
        f"/projects/{project_id}/notebooks/{notebook_id}",
        json={"name": "Market scan v2", "archived": True},
        headers=auth_headers(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Market scan v2"
    assert updated.json()["archived"] is True
    assert updated.json()["description"] == "Q3 competitors"  # untouched field kept

    assert (await api.delete(
        f"/projects/{project_id}/notebooks/{notebook_id}",
        headers=auth_headers(owner),
    )).status_code == 204
    assert (await api.get(
        f"/projects/{project_id}/notebooks", headers=auth_headers(owner)
    )).json() == []

    # And the physical row pattern: both tenant keys present on the table.
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        cols = await conn.fetch(
            """
            select column_name from information_schema.columns
            where table_schema = 'research' and table_name = 'notebooks'
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
    viewer = await user_factory("notebook-viewer")
    await _join_org(api, owner, org, viewer)
    await _invite_project(api, owner, org, viewer, project_id, "viewer")

    assert (await api.post(
        f"/projects/{project_id}/notebooks", json={"name": "nope"},
        headers=auth_headers(viewer),
    )).status_code == 403

    notebook = (await api.post(
        f"/projects/{project_id}/notebooks", json={"name": "target"},
        headers=auth_headers(owner),
    )).json()
    assert (await api.patch(
        f"/projects/{project_id}/notebooks/{notebook['id']}",
        json={"name": "rename"},
        headers=auth_headers(viewer),
    )).status_code == 403
    assert (await api.delete(
        f"/projects/{project_id}/notebooks/{notebook['id']}",
        headers=auth_headers(viewer),
    )).status_code == 403
    # Reads are fine.
    assert (await api.get(
        f"/projects/{project_id}/notebooks", headers=auth_headers(viewer)
    )).status_code == 200


async def test_unauthenticated_requests_are_rejected(api, owner: TestUser, org: str) -> None:
    project_id = await _project(api, owner, org)
    assert (await api.post(
        f"/projects/{project_id}/notebooks", json={"name": "x"}
    )).status_code == 401
    assert (await api.get(f"/projects/{project_id}/notebooks")).status_code == 401


async def test_guessed_project_id_returns_nothing(
    api, owner: TestUser, org: str, user_factory
) -> None:
    """IDs are not an oracle: no membership → 404, never the notebooks."""
    project_id = await _project(api, owner, org)
    stranger = await user_factory("notebook-stranger")
    response = await api.get(
        f"/projects/{project_id}/notebooks", headers=auth_headers(stranger)
    )
    assert response.status_code == 404

    ghost = str(uuid.uuid4())
    assert (await api.get(
        f"/projects/{ghost}/notebooks", headers=auth_headers(owner)
    )).status_code == 404


async def test_guessed_notebook_id_returns_nothing(
    api, owner: TestUser, org: str, user_factory
) -> None:
    project_id = await _project(api, owner, org)
    viewer = await user_factory("notebook-guesser")
    await _join_org(api, owner, org, viewer)
    await _invite_project(api, owner, org, viewer, project_id, "viewer")
    ghost = str(uuid.uuid4())
    assert (await api.patch(
        f"/projects/{project_id}/notebooks/{ghost}", json={"name": "x"},
        headers=auth_headers(owner),
    )).status_code == 404
    assert (await api.delete(
        f"/projects/{project_id}/notebooks/{ghost}", headers=auth_headers(owner)
    )).status_code == 404


async def test_client_supplied_ids_cannot_widen_scope(
    api, owner: TestUser, org: str
) -> None:
    """A body carrying another project_id/organization_id changes nothing:
    the URL project is the scope, derived server-side from the row."""
    project_id = await _project(api, owner, org)
    other_id = await _project(api, owner, org)
    response = await api.post(
        f"/projects/{project_id}/notebooks",
        json={"name": "scope-test", "project_id": other_id,
              "organization_id": str(uuid.uuid4())},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    assert response.json()["project_id"] == project_id
    assert response.json()["organization_id"] == org
    assert (await api.get(
        f"/projects/{other_id}/notebooks", headers=auth_headers(owner)
    )).json() == []


async def test_notebook_writes_are_audited(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await _project(api, owner, org)
    notebook = (await api.post(
        f"/projects/{project_id}/notebooks", json={"name": "audit-me"},
        headers=auth_headers(owner),
    )).json()
    await api.patch(
        f"/projects/{project_id}/notebooks/{notebook['id']}",
        json={"name": "audit-me-2"},
        headers=auth_headers(owner),
    )
    await api.delete(
        f"/projects/{project_id}/notebooks/{notebook['id']}",
        headers=auth_headers(owner),
    )
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        actions = [
            row["action"]
            for row in await conn.fetch(
                "select action from public.audit_log where organization_id = $1::uuid"
                " and action like 'notebook.%' order by id", org
            )
        ]
        assert actions == ["notebook.create", "notebook.update", "notebook.delete"]
    finally:
        await conn.close()
