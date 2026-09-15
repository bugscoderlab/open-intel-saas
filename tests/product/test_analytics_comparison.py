"""Managed HTTP seam: competitor comparison + service coverage
(ticket #55, spec #52, Phase 6 2/4).

Both metrics are project-scoped over the guarded ApprovedFactsSource
port. Facts are seeded through the real observation endpoints so the
approved/pending/superseded mix under test is the genuine lifecycle.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("comparison-owner")


@pytest_asyncio.fixture
async def outsider(user_factory) -> TestUser:
    return await user_factory("comparison-outsider")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("comparison-viewer")


async def _competitor(api, owner, project_id, name):
    response = await api.post(
        f"/projects/{project_id}/competitors",
        json={"name": name},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _service(api, owner, project_id, name):
    response = await api.post(
        f"/projects/{project_id}/services",
        json={"name": name},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _price(api, owner, project_id, competitor_id, service_id, amount, day):
    response = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/observations",
        json={
            "kind": "price",
            "service_id": service_id,
            "price_amount": amount,
            "price_currency": "MYR",
            "observed_on": day,
        },
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _approve(api, owner, project_id, observation_id):
    response = await api.post(
        f"/projects/{project_id}/observations/{observation_id}/approve",
        headers=auth_headers(owner),
    )
    assert response.status_code == 200, response.text


async def _seed_market(api, owner, project_id):
    """Two competitors x two services with a partial approved matrix."""
    paws = await _competitor(api, owner, project_id, "Paws")
    whiskers = await _competitor(api, owner, project_id, "Whiskers")
    grooming = await _service(api, owner, project_id, "Full grooming")
    trim = await _service(api, owner, project_id, "Nail trim")
    await _approve(
        api, owner, project_id,
        await _price(api, owner, project_id, paws, grooming, "88", "2026-09-01"),
    )
    await _approve(
        api, owner, project_id,
        await _price(api, owner, project_id, paws, trim, "25", "2026-09-01"),
    )
    # Whiskers covers grooming only; its trim price stays pending, and an
    # older grooming price is superseded by the newer approved one.
    old = await _price(api, owner, project_id, whiskers, grooming, "90", "2026-08-01")
    await _approve(api, owner, project_id, old)
    await _approve(
        api, owner, project_id,
        await _price(api, owner, project_id, whiskers, grooming, "95", "2026-09-05"),
    )
    pending = await _price(api, owner, project_id, whiskers, trim, "30", "2026-09-01")
    return paws, whiskers, grooming, trim, pending


class TestCompetitorComparison:
    async def test_matrix_shows_latest_approved_price_per_cell(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        paws, whiskers, grooming, trim, _ = await _seed_market(
            api, owner, project_id
        )

        response = await api.get(
            f"/projects/{project_id}/analytics/comparison",
            params={"competitor_ids": [paws, whiskers]},
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["metric"] == "competitor_comparison"
        assert payload["truncated"] is False

        cells = {
            (p["service_id"], p["competitor_id"]): p for p in payload["points"]
        }
        # Paws covers both services…
        assert cells[(grooming, paws)]["price_amount"] == "88.00"
        assert cells[(trim, paws)]["price_amount"] == "25.00"
        # …Whiskers covers grooming only; the pending trim price is an
        # absent cell, and the superseded 90 price is gone.
        assert cells[(grooming, whiskers)]["price_amount"] == "95.00"
        assert (trim, whiskers) not in cells
        assert {p["competitor_name"] for p in payload["points"]} == {
            "Paws",
            "Whiskers",
        }

    async def test_competitor_ids_outside_project_are_silently_excluded(
        self, api, owner, org
    ):
        project_id = await new_project(api, owner, org)
        paws, _, _, _, _ = await _seed_market(api, owner, project_id)
        other_project = await new_project(api, owner, org)
        stranger = await _competitor(api, owner, other_project, "Stranger")

        response = await api.get(
            f"/projects/{project_id}/analytics/comparison",
            params={"competitor_ids": [paws, stranger]},
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        assert {p["competitor_id"] for p in response.json()["points"]} == {paws}

    async def test_omitted_filter_covers_all_project_competitors(
        self, api, owner, org
    ):
        project_id = await new_project(api, owner, org)
        paws, whiskers, _, _, _ = await _seed_market(api, owner, project_id)

        response = await api.get(
            f"/projects/{project_id}/analytics/comparison",
            headers=auth_headers(owner),
        )
        assert response.status_code == 200
        assert {p["competitor_id"] for p in response.json()["points"]} == {
            paws,
            whiskers,
        }

    async def test_outsider_is_forbidden(self, api, owner, outsider, org):
        project_id = await new_project(api, owner, org)
        await _seed_market(api, owner, project_id)
        denied = await api.get(
            f"/projects/{project_id}/analytics/comparison",
            headers=auth_headers(outsider),
        )
        assert denied.status_code in (403, 404)


class TestServiceCoverage:
    async def test_coverage_counts_and_uncovered_names(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        paws, whiskers, grooming, trim, _ = await _seed_market(api, owner, project_id)

        response = await api.get(
            f"/projects/{project_id}/analytics/service-coverage",
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        points = {p["competitor_id"]: p for p in response.json()["points"]}
        assert points[paws]["covered"] == 2
        assert points[paws]["uncovered_service_names"] == []
        assert points[whiskers]["covered"] == 1
        assert points[whiskers]["uncovered_service_names"] == ["Nail trim"]
        assert points[paws]["total"] == 2

    async def test_viewer_reads_coverage(self, api, owner, viewer, org):
        project_id = await new_project(api, owner, org)
        await _seed_market(api, owner, project_id)
        invited = await api.post(
            f"/organizations/{org}/invitations",
            json={
                "email": viewer.email,
                "scope": "project",
                "role": "viewer",
                "project_id": project_id,
            },
            headers=auth_headers(owner),
        )
        assert invited.status_code == 201, invited.text
        token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit("token=", 1)[1]
        accepted = await api.post(
            "/invitations/accept", json={"token": token}, headers=auth_headers(viewer)
        )
        assert accepted.status_code == 204

        response = await api.get(
            f"/projects/{project_id}/analytics/service-coverage",
            headers=auth_headers(viewer),
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["points"]) == 2
