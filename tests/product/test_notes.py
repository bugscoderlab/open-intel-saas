"""HTTP seam: Notes CRUD (ticket #30, spec #26, Phase 2 backfill 3/3).

A Note belongs to a Notebook and carries the tenant scope like every
research row (organization_id + project_id). Covers the acceptance
criteria: full CRUD shapes, tenant isolation (the tenant-safe 404), the
permission matrix (viewer read-only), notebook cascade, and audit.
"""

from __future__ import annotations

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_notebook, new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("notes-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("notes-viewer")


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


async def _create_note(api, user: TestUser, project_id: str, notebook_id: str, **body):
    return await api.post(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes",
        json=body,
        headers=auth_headers(user),
    )


async def _audit_entries(settings, organization_id: str, target_id: str) -> list[dict]:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        rows = await conn.fetch(
            "select action from public.audit_log"
            " where organization_id = $1::uuid and target_id = $2"
            " order by created_at",
            organization_id,
            target_id,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def test_note_crud_lifecycle(api, owner: TestUser, org: str) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)

    created = await _create_note(
        api, owner, project_id, notebook_id, title="Pricing", content="RM88 in Sept"
    )
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["notebook_id"] == notebook_id
    assert note["organization_id"] == org
    assert note["project_id"] == project_id
    assert note["title"] == "Pricing"
    note_id = note["id"]

    listed = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes",
        headers=auth_headers(owner),
    )
    assert listed.status_code == 200, listed.text
    assert [n["id"] for n in listed.json()] == [note_id]

    fetched = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(owner),
    )
    assert fetched.status_code == 200
    assert fetched.json()["content"] == "RM88 in Sept"

    updated = await api.patch(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        json={"content": "RM88 in Sept, RM90 in Oct"},
        headers=auth_headers(owner),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["content"] == "RM88 in Sept, RM90 in Oct"

    deleted = await api.delete(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(owner),
    )
    assert deleted.status_code == 204
    gone = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(owner),
    )
    assert gone.status_code == 404


async def test_notes_are_isolated_between_organizations(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    created = await _create_note(
        api, owner, project_id, notebook_id, title="Secret", content="private"
    )
    note_id = created.json()["id"]

    # A user from another organization guessing the IDs: tenant-safe 404s.
    assert (
        await api.get(
            f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
            headers=auth_headers(viewer),
        )
    ).status_code == 404
    assert (
        await api.patch(
            f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
            json={"title": "hijack"},
            headers=auth_headers(viewer),
        )
    ).status_code == 404
    assert (
        await api.delete(
            f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
            headers=auth_headers(viewer),
        )
    ).status_code == 404


async def test_project_viewer_reads_but_cannot_write(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    await _invite_project_viewer(api, owner, org, viewer, project_id)
    notebook_id = await new_notebook(api, owner, project_id)
    created = await _create_note(
        api, owner, project_id, notebook_id, title="Shared", content="visible"
    )
    note_id = created.json()["id"]

    read = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(viewer),
    )
    assert read.status_code == 200

    list_response = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes",
        headers=auth_headers(viewer),
    )
    assert list_response.status_code == 200

    denied_create = await _create_note(
        api, viewer, project_id, notebook_id, title="Nope", content="x"
    )
    assert denied_create.status_code == 403
    denied_update = await api.patch(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        json={"title": "Nope"},
        headers=auth_headers(viewer),
    )
    assert denied_update.status_code == 403
    denied_delete = await api.delete(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(viewer),
    )
    assert denied_delete.status_code == 403

    # the note is untouched
    still = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(owner),
    )
    assert still.json()["title"] == "Shared"


async def test_deleting_the_notebook_cascades_to_notes(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    created = await _create_note(
        api, owner, project_id, notebook_id, title="Doomed", content="x"
    )
    note_id = created.json()["id"]

    deleted = await api.delete(
        f"/projects/{project_id}/notebooks/{notebook_id}",
        headers=auth_headers(owner),
    )
    assert deleted.status_code == 204

    gone = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(owner),
    )
    assert gone.status_code == 404


async def test_note_writes_are_audited(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    created = await _create_note(
        api, owner, project_id, notebook_id, title="Audited", content="x"
    )
    note_id = created.json()["id"]
    await api.patch(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        json={"content": "y"},
        headers=auth_headers(owner),
    )
    await api.delete(
        f"/projects/{project_id}/notebooks/{notebook_id}/notes/{note_id}",
        headers=auth_headers(owner),
    )

    actions = [
        entry["action"]
        for entry in await _audit_entries(settings, org, note_id)
    ]
    assert actions == ["note.create", "note.update", "note.delete"]


async def test_notes_in_other_notebooks_do_not_leak(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_a = await new_notebook(api, owner, project_id)
    notebook_b = await new_notebook(api, owner, project_id)
    await _create_note(
        api, owner, project_id, notebook_b, title="B note", content="x"
    )

    listed = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_a}/notes",
        headers=auth_headers(owner),
    )
    assert listed.json() == []

    # guessing a note from notebook B under notebook A: 404
    note_b = (
        await _create_note(api, owner, project_id, notebook_b, title="B2", content="y")
    ).json()
    guessed = await api.get(
        f"/projects/{project_id}/notebooks/{notebook_a}/notes/{note_b['id']}",
        headers=auth_headers(owner),
    )
    assert guessed.status_code == 404
