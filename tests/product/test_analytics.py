"""Managed HTTP seam: analytics read foundation (ticket #54, spec #52,
Phase 6 1/4).

The price-trend metric is the first registered metric over the
ApprovedFactsSource port: approved, non-superseded observations only,
tenant-scoped, with the statement timeout + row-cap guardrails. Facts
are seeded through the real observation endpoints (manual create →
review queue approve) so the approved/pending/rejected/superseded
states under test are the genuine lifecycle, not SQL fixtures.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("analytics-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("analytics-viewer")


@pytest_asyncio.fixture
async def outsider(user_factory) -> TestUser:
    """A confirmed user belonging to NO organization — cross-tenant."""
    return await user_factory("analytics-outsider")


async def _new_competitor(api, owner: TestUser, project_id: str, name: str) -> str:
    response = await api.post(
        f"/projects/{project_id}/competitors",
        json={"name": name},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _propose_price(
    api, owner: TestUser, project_id: str, competitor_id: str, amount: str
) -> str:
    """Manual observation entries land pending; returns observation id."""
    response = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/observations",
        json={
            "kind": "price",
            "price_amount": amount,
            "price_currency": "MYR",
            "observed_on": "2026-09-01",
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
    return response


async def _trend(api, user: TestUser, project_id: str, competitor_id: str):
    return await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}"
        "/analytics/price-trend",
        headers=auth_headers(user),
    )


class TestPriceTrend:
    async def test_trend_serves_only_approved_non_superseded(
        self, api, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")

        approved_id = await _propose_price(api, owner, project_id, competitor_id, "88")
        await _approve(api, owner, project_id, approved_id)

        # Same cell, newer value: approving it supersedes the first row.
        superseding_id = await _propose_price(
            api, owner, project_id, competitor_id, "95"
        )
        await _approve(api, owner, project_id, superseding_id)

        # A pending and a rejected row must never reach analytics.
        await _propose_price(api, owner, project_id, competitor_id, "50")
        rejected_id = await _propose_price(
            api, owner, project_id, competitor_id, "40"
        )
        rejected = await api.post(
            f"/projects/{project_id}/observations/{rejected_id}/reject",
            headers=auth_headers(owner),
        )
        assert rejected.status_code == 200

        response = await _trend(api, owner, project_id, competitor_id)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["metric"] == "price_trend"
        assert payload["truncated"] is False
        assert len(payload["points"]) == 1  # only the current approved value
        assert Decimal(payload["points"][0]["price_amount"]) == Decimal("95")
        assert payload["points"][0]["price_currency"] == "MYR"

    async def test_trend_orders_points_by_observed_on(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        # Two different services (catalog rows) — each its own series point.
        services = []
        for name in ("Full grooming", "Nail trim"):
            created = await api.post(
                f"/projects/{project_id}/services",
                json={"name": name},
                headers=auth_headers(owner),
            )
            assert created.status_code == 201, created.text
            services.append(created.json()["id"])
        for service_id, amount in zip(services, ("88", "25"), strict=True):
            proposed = await api.post(
                f"/projects/{project_id}/competitors/{competitor_id}/observations",
                json={
                    "kind": "price",
                    "service_id": service_id,
                    "price_amount": amount,
                    "price_currency": "MYR",
                    "observed_on": "2026-09-01",
                },
                headers=auth_headers(owner),
            )
            assert proposed.status_code == 201, proposed.text
            await _approve(api, owner, project_id, proposed.json()["id"])

        response = await _trend(api, owner, project_id, competitor_id)
        assert response.status_code == 200
        points = response.json()["points"]
        assert {p["service_id"] for p in points} == set(services)

    async def test_viewer_reads_trend_outsider_forbidden(
        self, api, owner, viewer, outsider, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        approved_id = await _propose_price(api, owner, project_id, competitor_id, "88")
        await _approve(api, owner, project_id, approved_id)

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

        as_viewer = await _trend(api, viewer, project_id, competitor_id)
        assert as_viewer.status_code == 200, as_viewer.text

        # A user from ANOTHER organization gets no tenant access.
        denied = await _trend(api, outsider, project_id, competitor_id)
        assert denied.status_code in (403, 404)

    async def test_row_cap_truncates_instead_of_erroring(
        self, api, owner, org, settings
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        # Three catalog services: distinct comparison cells, so all
        # three approved prices survive (same-cell approvals supersede).
        for i, amount in enumerate(("88", "95", "105")):
            service = await api.post(
                f"/projects/{project_id}/services",
                json={"name": f"Service {i}"},
                headers=auth_headers(owner),
            )
            assert service.status_code == 201, service.text
            proposed = await api.post(
                f"/projects/{project_id}/competitors/{competitor_id}/observations",
                json={
                    "kind": "price",
                    "service_id": service.json()["id"],
                    "price_amount": amount,
                    "price_currency": "MYR",
                    "observed_on": "2026-09-01",
                },
                headers=auth_headers(owner),
            )
            assert proposed.status_code == 201, proposed.text
            await _approve(api, owner, project_id, proposed.json()["id"])

        # Shrink the guardrail on the wired source: the metric must
        # truncate and flag, not fail.
        api.app.state.analytics_facts_source.row_cap = 2
        response = await _trend(api, owner, project_id, competitor_id)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["truncated"] is True
        assert len(payload["points"]) == 2
