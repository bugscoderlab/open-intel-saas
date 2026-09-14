"""HTTP seam: evidence links — competitor↔source/notebook connection
(ticket #35, spec #31, Phase 3 3/3).

Target IDs are opaque UUIDs: no research FK, no cross-module existence
check in Phase 3 (spec #31 assumption 4 — Phase 5 adds it behind the
module-enabled check). Manual attaches land approved; deleting an
observation nulls its links' observation_id and retains them on the
competitor (migration 0017).
"""

from __future__ import annotations

import uuid
from datetime import date

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("evd-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("evd-viewer")


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


async def _new_competitor(api, user: TestUser, project_id: str, name: str) -> dict:
    response = await api.post(
        f"/projects/{project_id}/competitors",
        json={"name": name},
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _new_observation(
    api, user: TestUser, project_id: str, competitor_id: str
) -> dict:
    response = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/observations",
        json={
            "price_amount": "88.00",
            "price_currency": "MYR",
            "observed_on": str(date(2026, 9, 1)),
        },
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_evidence(
    api, user: TestUser, project_id: str, competitor_id: str, **fields
) -> dict:
    body = {
        "target_kind": "source",
        "target_id": str(uuid.uuid4()),
        "observation_id": None,
        "excerpt": None,
        "excerpt_start": None,
        "excerpt_end": None,
    }
    body.update(fields)
    response = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/evidence",
        json=body,
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_manual_attach_lands_approved_with_excerpt(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    target_id = uuid.uuid4()

    link = await _add_evidence(
        api,
        owner,
        project_id,
        competitor["id"],
        target_id=str(target_id),
        excerpt="Full grooming RM 88 this month",
        excerpt_start=12,
        excerpt_end=30,
    )
    assert link["approval_state"] == "approved"
    assert link["target_kind"] == "source"
    assert link["target_id"] == str(target_id)
    assert link["excerpt"] == "Full grooming RM 88 this month"
    assert link["excerpt_start"] == 12
    assert link["excerpt_end"] == 30
    assert link["observation_id"] is None


async def test_both_target_kinds_accepted_invalid_kind_is_422(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")

    notebook_link = await _add_evidence(
        api, owner, project_id, competitor["id"],
        target_kind="notebook", target_id=str(uuid.uuid4()),
    )
    assert notebook_link["target_kind"] == "notebook"

    bad = await api.post(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        json={"target_kind": "tweet", "target_id": str(uuid.uuid4())},
        headers=auth_headers(owner),
    )
    assert bad.status_code == 422


async def test_excerpt_offsets_must_point_forward(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    bad = await api.post(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        json={
            "target_kind": "source",
            "target_id": str(uuid.uuid4()),
            "excerpt": "x",
            "excerpt_start": 30,
            "excerpt_end": 12,
        },
        headers=auth_headers(owner),
    )
    assert bad.status_code == 422


async def test_list_filters_by_kind_and_observation(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    observation = await _new_observation(api, owner, project_id, competitor["id"])

    source_link = await _add_evidence(api, owner, project_id, competitor["id"])
    notebook_link = await _add_evidence(
        api, owner, project_id, competitor["id"],
        target_kind="notebook", target_id=str(uuid.uuid4()),
    )
    observation_link = await _add_evidence(
        api, owner, project_id, competitor["id"],
        observation_id=observation["id"],
    )

    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        headers=auth_headers(owner),
    )
    assert [row["id"] for row in listed.json()] == [
        source_link["id"],
        notebook_link["id"],
        observation_link["id"],
    ]

    sources_only = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence"
        "?target_kind=source",
        headers=auth_headers(owner),
    )
    assert [row["id"] for row in sources_only.json()] == [
        source_link["id"],
        observation_link["id"],
    ]

    for_observation = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence"
        f"?observation_id={observation['id']}",
        headers=auth_headers(owner),
    )
    assert [row["id"] for row in for_observation.json()] == [observation_link["id"]]


async def test_delete_removes_the_link_only(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    link = await _add_evidence(api, owner, project_id, competitor["id"])

    deleted = await api.delete(
        f"/projects/{project_id}/competitors/{competitor['id']}"
        f"/evidence/{link['id']}",
        headers=auth_headers(owner),
    )
    assert deleted.status_code == 204
    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        headers=auth_headers(owner),
    )
    assert listed.json() == []
    # deleting again is a tenant-safe 404
    again = await api.delete(
        f"/projects/{project_id}/competitors/{competitor['id']}"
        f"/evidence/{link['id']}",
        headers=auth_headers(owner),
    )
    assert again.status_code == 404


async def test_deleting_an_observation_nulls_its_links(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    observation = await _new_observation(api, owner, project_id, competitor["id"])
    link = await _add_evidence(
        api, owner, project_id, competitor["id"],
        observation_id=observation["id"],
    )

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "delete from competitor.observations where id = $1",
            uuid.UUID(observation["id"]),
        )
    finally:
        await conn.close()

    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        headers=auth_headers(owner),
    )
    assert len(listed.json()) == 1
    retained = listed.json()[0]
    assert retained["id"] == link["id"]
    assert retained["observation_id"] is None


async def test_link_under_another_competitor_is_a_404(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor_a = await _new_competitor(api, owner, project_id, "Paw Spa")
    competitor_b = await _new_competitor(api, owner, project_id, "Rival Co")
    link = await _add_evidence(api, owner, project_id, competitor_a["id"])

    stolen = await api.get(
        f"/projects/{project_id}/competitors/{competitor_b['id']}/evidence"
        f"?observation_id={uuid.uuid4()}",
        headers=auth_headers(owner),
    )
    assert stolen.status_code == 200  # list is scoped, simply empty
    assert stolen.json() == []
    delete_from_b = await api.delete(
        f"/projects/{project_id}/competitors/{competitor_b['id']}"
        f"/evidence/{link['id']}",
        headers=auth_headers(owner),
    )
    assert delete_from_b.status_code == 404


async def test_viewer_reads_but_cannot_attach_or_delete(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    await _invite_project_viewer(api, owner, org, viewer, project_id)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    link = await _add_evidence(api, owner, project_id, competitor["id"])

    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        headers=auth_headers(viewer),
    )
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [link["id"]]

    denied_attach = await api.post(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        json={"target_kind": "source", "target_id": str(uuid.uuid4())},
        headers=auth_headers(viewer),
    )
    assert denied_attach.status_code == 403
    denied_delete = await api.delete(
        f"/projects/{project_id}/competitors/{competitor['id']}"
        f"/evidence/{link['id']}",
        headers=auth_headers(viewer),
    )
    assert denied_delete.status_code == 403


async def test_evidence_is_isolated_between_organizations(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Secret Co")
    await _add_evidence(api, owner, project_id, competitor["id"])

    outsider_list = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        headers=auth_headers(viewer),
    )
    assert outsider_list.status_code == 404
    outsider_attach = await api.post(
        f"/projects/{project_id}/competitors/{competitor['id']}/evidence",
        json={"target_kind": "source", "target_id": str(uuid.uuid4())},
        headers=auth_headers(viewer),
    )
    assert outsider_attach.status_code == 404
