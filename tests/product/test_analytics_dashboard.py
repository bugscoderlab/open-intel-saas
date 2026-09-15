"""Managed HTTP seam: dashboard payload + CSV export (ticket #57,
spec #52, Phase 6 4/4).

The dashboard endpoint assembles per-competitor widget sections from the
SAME metric functions as the individual endpoints; the changes section
reads the durable superseded-row model. CSV export renders registered
metrics row-for-row, including RFC 4180 quoting of values containing
commas.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("dashboard-owner")


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


async def _seed(api, owner, project_id):
    paws = await _competitor(api, owner, project_id, "Paws")
    grooming = await _service(api, owner, project_id, "Full grooming, deluxe")
    first = await _price(api, owner, project_id, paws, grooming, "88", "2026-08-01")
    await _approve(api, owner, project_id, first)
    second = await _price(api, owner, project_id, paws, grooming, "95", "2026-09-01")
    await _approve(api, owner, project_id, second)
    return paws, grooming, first, second


class TestDashboard:
    async def test_dashboard_assembles_widget_sections_and_changes(
        self, api, owner, org
    ):
        project_id = await new_project(api, owner, org)
        paws, _, first, second = await _seed(api, owner, project_id)

        response = await api.get(
            f"/projects/{project_id}/analytics/dashboard",
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["project_id"] == project_id
        assert payload["truncated"] is False
        assert len(payload["competitors"]) == 1

        section = payload["competitors"][0]
        assert section["competitor_id"] == paws
        # Price trend carries the current approved value only…
        assert [p["price_amount"] for p in section["price_trend"]] == ["95.00"]
        # …the comparison shows the cell with its (comma-bearing) name…
        assert section["comparison"][0]["service_name"] == "Full grooming, deluxe"
        # …coverage is complete…
        assert section["service_coverage"]["covered"] == 1
        assert section["service_coverage"]["total"] == 1
        # …and the changes section records the superseded row.
        assert [c["observation_id"] for c in section["changes"]] == [first]
        assert section["changes"][0]["superseded_by"] == second
        assert section["review_topics"] == []


class TestCsvExport:
    async def test_export_price_trend_row_for_row(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        paws, _, _, _ = await _seed(api, owner, project_id)

        response = await api.get(
            f"/projects/{project_id}/analytics/export.csv",
            params={"metric": "price_trend", "competitor_ids": [paws]},
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        assert "price_trend" in response.headers["content-disposition"]
        lines = response.text.split("\r\n")
        assert lines[0].startswith("metric,price_trend,unit,price")
        header = lines[1].split(",")
        rows = [
            dict(zip(header, line.split(","), strict=True))
            for line in lines[2:]
            if line
        ]
        assert len(rows) == 1  # superseded 88 row excluded
        assert rows[0]["price_amount"] == "95.00"

    async def test_export_comparison_quotes_comma_values(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        paws, _, _, _ = await _seed(api, owner, project_id)

        response = await api.get(
            f"/projects/{project_id}/analytics/export.csv",
            params={"metric": "competitor_comparison", "competitor_ids": [paws]},
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        # The service name contains a comma — RFC 4180 requires quoting.
        assert '"Full grooming, deluxe"' in response.text
        lines = [line for line in response.text.split("\r\n") if line]
        assert len(lines) == 3  # meta row + header + one data row

    async def test_export_review_topics(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        paws, grooming, _, _ = await _seed(api, owner, project_id)
        response = await api.get(
            f"/projects/{project_id}/analytics/export.csv",
            params={"metric": "service_coverage", "competitor_ids": [paws]},
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        assert "uncovered_service_names" in response.text.split("\r\n")[1]

    async def test_unknown_metric_is_a_400(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        await _seed(api, owner, project_id)
        response = await api.get(
            f"/projects/{project_id}/analytics/export.csv",
            params={"metric": "haiku"},
            headers=auth_headers(owner),
        )
        assert response.status_code == 422  # the platform's typed-validation status
