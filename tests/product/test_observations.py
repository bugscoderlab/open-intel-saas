"""HTTP seam: service catalog, price Observations, review queue, Change
events (ticket #34, spec #31, Phase 3 2/3).

Facts are stored, never overwritten (glossary): approval of a different
value supersedes the prior approved row and emits exactly one
CompetitorChangeDetected outbox event in the same transaction; identical
re-observations emit none; rejects are retained for audit.
"""

from __future__ import annotations

import json
from datetime import date

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("obs-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("obs-viewer")


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


async def _new_service(api, user: TestUser, project_id: str, name: str) -> dict:
    response = await api.post(
        f"/projects/{project_id}/services",
        json={"name": name},
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _new_observation(
    api, user: TestUser, project_id: str, competitor_id: str, **fields
) -> dict:
    body = {
        "service_id": None,
        "location_id": None,
        "price_amount": "88.00",
        "price_currency": "MYR",
        "observed_on": str(date(2026, 9, 1)),
    }
    body.update(fields)
    response = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/observations",
        json=body,
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _change_events(settings, organization_id: str) -> list[dict]:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        rows = await conn.fetch(
            "select payload from public.outbox_events"
            " where event_type = 'CompetitorChangeDetected'"
            " and payload->>'organization_id' = $1"
            " order by occurred_at",
            organization_id,
        )
        return [json.loads(row["payload"]) for row in rows]
    finally:
        await conn.close()


async def test_service_catalog_dedupes_case_insensitively(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    created = await _new_service(api, owner, project_id, "Full grooming")
    assert created["name"] == "Full grooming"

    duplicate = await api.post(
        f"/projects/{project_id}/services",
        json={"name": "FULL GROOMING"},
        headers=auth_headers(owner),
    )
    assert duplicate.status_code == 409

    listed = await api.get(
        f"/projects/{project_id}/services", headers=auth_headers(owner)
    )
    assert [s["name"] for s in listed.json()] == ["Full grooming"]


async def test_in_use_service_cannot_be_deleted(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    service = await _new_service(api, owner, project_id, "Full grooming")
    await _new_observation(
        api, owner, project_id, competitor["id"], service_id=service["id"]
    )
    delete = await api.delete(
        f"/projects/{project_id}/services/{service['id']}",
        headers=auth_headers(owner),
    )
    assert delete.status_code == 409

    unused = await _new_service(api, owner, project_id, "Nail trim")
    ok = await api.delete(
        f"/projects/{project_id}/services/{unused['id']}",
        headers=auth_headers(owner),
    )
    assert ok.status_code == 204


async def test_pending_observation_flows_through_review_queue(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    service = await _new_service(api, owner, project_id, "Full grooming")

    observation = await _new_observation(
        api, owner, project_id, competitor["id"], service_id=service["id"]
    )
    assert observation["approval_state"] == "pending"
    assert observation["confidence"] == "1.0"
    assert observation["extraction_version"] == "manual-v1"
    observation_id = observation["id"]

    queue = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
    )
    assert [o["id"] for o in queue.json()] == [observation_id]

    approved = await api.post(
        f"/projects/{project_id}/observations/{observation_id}/approve",
        headers=auth_headers(owner),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_state"] == "approved"

    queue_after = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
    )
    assert queue_after.json() == []


async def test_approval_of_a_different_price_supersedes_and_emits_change(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    service = await _new_service(api, owner, project_id, "Full grooming")

    first = await _new_observation(
        api, owner, project_id, competitor["id"],
        service_id=service["id"], price_amount="88.00",
    )
    await api.post(
        f"/projects/{project_id}/observations/{first['id']}/approve",
        headers=auth_headers(owner),
    )

    second = await _new_observation(
        api, owner, project_id, competitor["id"],
        service_id=service["id"], price_amount="95.00",
        observed_on=str(date(2026, 9, 10)),
    )
    approved = await api.post(
        f"/projects/{project_id}/observations/{second['id']}/approve",
        headers=auth_headers(owner),
    )
    assert approved.status_code == 200, approved.text

    # the first row is superseded and points at its successor
    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/observations",
        headers=auth_headers(owner),
    )
    by_id = {o["id"]: o for o in listed.json()}
    assert by_id[first["id"]]["approval_state"] == "superseded"
    assert by_id[first["id"]]["superseded_by"] == second["id"]
    assert by_id[second["id"]]["approval_state"] == "approved"

    events = await _change_events(settings, org)
    assert len(events) == 1
    payload = events[0]
    assert payload["previous_observation_id"] == first["id"]
    assert payload["new_observation_id"] == second["id"]
    assert payload["previous_price_amount"] == "88.00"
    assert payload["new_price_amount"] == "95.00"
    assert payload["price_currency"] == "MYR"
    assert payload["competitor_id"] == competitor["id"]


async def test_identical_reobservation_is_not_a_change(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    service = await _new_service(api, owner, project_id, "Full grooming")

    first = await _new_observation(
        api, owner, project_id, competitor["id"],
        service_id=service["id"], price_amount="88.00",
    )
    await api.post(
        f"/projects/{project_id}/observations/{first['id']}/approve",
        headers=auth_headers(owner),
    )
    again = await _new_observation(
        api, owner, project_id, competitor["id"],
        service_id=service["id"], price_amount="88.00",
        observed_on=str(date(2026, 9, 11)),
    )
    await api.post(
        f"/projects/{project_id}/observations/{again['id']}/approve",
        headers=auth_headers(owner),
    )
    assert (await _change_events(settings, org)) == []


async def test_location_scoped_facts_are_separate_cells(
    api, owner: TestUser, org: str, settings
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    service = await _new_service(api, owner, project_id, "Full grooming")
    location = (
        await api.post(
            f"/projects/{project_id}/competitors/{competitor['id']}/locations",
            json={"name": "Downtown"},
            headers=auth_headers(owner),
        )
    ).json()

    market_level = await _new_observation(
        api, owner, project_id, competitor["id"],
        service_id=service["id"], price_amount="88.00",
    )
    await api.post(
        f"/projects/{project_id}/observations/{market_level['id']}/approve",
        headers=auth_headers(owner),
    )
    branch_level = await _new_observation(
        api, owner, project_id, competitor["id"],
        service_id=service["id"], location_id=location["id"],
        price_amount="92.00",
    )
    await api.post(
        f"/projects/{project_id}/observations/{branch_level['id']}/approve",
        headers=auth_headers(owner),
    )
    # a different cell: no supersede, no Change
    assert (await _change_events(settings, org)) == []
    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/observations",
        headers=auth_headers(owner),
    )
    by_id = {o["id"]: o for o in listed.json()}
    assert by_id[market_level["id"]]["approval_state"] == "approved"
    assert by_id[branch_level["id"]]["approval_state"] == "approved"


async def test_rejected_observation_is_retained_but_leaves_the_queue(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")

    observation = await _new_observation(
        api, owner, project_id, competitor["id"], price_amount="1.00"
    )
    rejected = await api.post(
        f"/projects/{project_id}/observations/{observation['id']}/reject",
        headers=auth_headers(owner),
    )
    assert rejected.status_code == 200
    assert rejected.json()["approval_state"] == "rejected"

    queue = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
    )
    assert queue.json() == []
    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/observations",
        headers=auth_headers(owner),
    )
    assert [o["approval_state"] for o in listed.json()] == ["rejected"]


async def test_non_pending_observation_cannot_be_approved_twice(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    observation = await _new_observation(
        api, owner, project_id, competitor["id"]
    )
    await api.post(
        f"/projects/{project_id}/observations/{observation['id']}/approve",
        headers=auth_headers(owner),
    )
    again = await api.post(
        f"/projects/{project_id}/observations/{observation['id']}/approve",
        headers=auth_headers(owner),
    )
    assert again.status_code == 409


async def test_viewer_reads_queue_but_cannot_review_or_create(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    await _invite_project_viewer(api, owner, org, viewer, project_id)
    competitor = await _new_competitor(api, owner, project_id, "Paw Spa")
    observation = await _new_observation(
        api, owner, project_id, competitor["id"]
    )

    queue = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(viewer)
    )
    assert queue.status_code == 200
    listed = await api.get(
        f"/projects/{project_id}/competitors/{competitor['id']}/observations",
        headers=auth_headers(viewer),
    )
    assert listed.status_code == 200

    denied_review = await api.post(
        f"/projects/{project_id}/observations/{observation['id']}/approve",
        headers=auth_headers(viewer),
    )
    assert denied_review.status_code == 403
    denied_create = await api.post(
        f"/projects/{project_id}/competitors/{competitor['id']}/observations",
        json={
            "price_amount": "10.00",
            "price_currency": "MYR",
            "observed_on": str(date(2026, 9, 12)),
        },
        headers=auth_headers(viewer),
    )
    assert denied_create.status_code == 403


async def test_observations_are_isolated_between_organizations(
    api, owner: TestUser, viewer: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    competitor = await _new_competitor(api, owner, project_id, "Secret Co")
    observation = await _new_observation(
        api, owner, project_id, competitor["id"]
    )

    assert (
        await api.get(
            f"/projects/{project_id}/competitors/{competitor['id']}/observations",
            headers=auth_headers(viewer),
        )
    ).status_code == 404
    assert (
        await api.post(
            f"/projects/{project_id}/observations/{observation['id']}/approve",
            headers=auth_headers(viewer),
        )
    ).status_code == 404
    assert (
        await api.get(
            f"/projects/{project_id}/review-queue",
            headers=auth_headers(viewer),
        )
    ).status_code == 404
