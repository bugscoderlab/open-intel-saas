"""Managed HTTP seam: the human approval queue between proposed and
durable facts (ticket #51, spec #47, Phase 5 3/3).

The queue/approve/reject mechanics shipped with phase 3 (ticket #34);
this suite verifies them against EXTRACTION-proposed observations (the
phase-5 workload) and the new approved-only listing — the feed phase 6
consumes. Facts under test: pending → approved/rejected only,
supersede-on-new-value, strict 409s, viewer read / editor review.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.extraction.application.services.extract_service import (
    drain_pending_extractions,
)
from modules.extraction.domain.entities import ExtractedItem, ExtractionResult
from modules.extraction.infrastructure.unit_of_work import SqlExtractionUnit
from modules.platform.infrastructure.db import create_engine
from tests.product.conftest import TestUser, auth_headers
from tests.product.extraction_helpers import TestObservationSink, TestSnapshotSource
from tests.product.fakes import FakeExtractor, FakeWebsiteFetcher
from tests.product.research_helpers import new_project

URL = "https://paws.example.com/pricing"
PAGE_V1 = "<html><body>Full grooming RM88</body></html>"
PAGE_V2 = "<html><body>Full grooming RM95</body></html>"


def _price_result(amount: str) -> ExtractionResult:
    return ExtractionResult(
        items=(
            ExtractedItem(
                kind="price",
                claim=f"Full grooming — RM{amount}",
                price_amount=Decimal(amount),
                price_currency="MYR",
                confidence=Decimal("0.95"),
                excerpt=f"Full grooming RM{amount}",
            ),
        )
    )


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("approval-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("approval-viewer")


@pytest_asyncio.fixture
async def extract_drain(
    settings,
) -> AsyncIterator[Callable[[FakeExtractor], Awaitable[int]]]:
    engine = create_engine(settings.database_dsn)

    async def _drain(extractor: FakeExtractor) -> int:
        return await drain_pending_extractions(
            lambda: SqlExtractionUnit(engine),
            extractor,
            TestSnapshotSource(engine),
            TestObservationSink(engine),
        )

    yield _drain
    await engine.dispose()


async def _propose_price(
    api, drain, extract_drain, owner: TestUser, project_id: str, page: str, amount: str
) -> str:
    """Collect a page, extract one price fact, return the observation id.
    Reuses the project's first competitor so repeated proposals target
    the same comparison cell."""
    existing = await api.get(
        f"/projects/{project_id}/competitors", headers=auth_headers(owner)
    )
    competitors = existing.json()
    if competitors:
        competitor_id = competitors[0]["id"]
    else:
        response = await api.post(
            f"/projects/{project_id}/competitors",
            json={"name": "Paws"},
            headers=auth_headers(owner),
        )
        assert response.status_code == 201, response.text
        competitor_id = response.json()["id"]
    queued = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/collections",
        json={"connector_kind": "website", "url": URL},
        headers=auth_headers(owner),
    )
    assert queued.status_code == 202, queued.text
    await drain(FakeWebsiteFetcher(pages={URL: page}))
    listing = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
        headers=auth_headers(owner),
    )
    snapshot_id = listing.json()[0]["id"]
    run = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}"
        f"/snapshots/{snapshot_id}/extract",
        headers=auth_headers(owner),
    )
    assert run.status_code == 202, run.text
    await extract_drain(FakeExtractor(results={page: _price_result(amount)}))
    queue = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
    )
    observations = queue.json()
    assert len(observations) == 1
    return observations[0]["id"]


async def _approve(api, user: TestUser, project_id: str, observation_id: str):
    return await api.post(
        f"/projects/{project_id}/observations/{observation_id}/approve",
        headers=auth_headers(user),
    )


async def _reject(api, user: TestUser, project_id: str, observation_id: str):
    return await api.post(
        f"/projects/{project_id}/observations/{observation_id}/reject",
        headers=auth_headers(user),
    )


async def _approved(api, user: TestUser, project_id: str, competitor_id: str):
    response = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}/observations/approved",
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _invite_viewer(api, owner: TestUser, org, viewer: TestUser, project_id: str):
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


async def _sole_pending_competitor(api, user: TestUser, project_id: str) -> str:
    queue = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(user)
    )
    assert queue.status_code == 200, queue.text
    return queue.json()[0]["competitor_id"]


class TestApprovalQueue:
    async def test_proposed_fact_flows_through_review_to_approved_listing(
        self, api, drain, extract_drain, owner, org
    ):
        project_id = await new_project(api, owner, org)
        observation_id = await _propose_price(
            api, drain, extract_drain, owner, project_id, PAGE_V1, "88"
        )
        competitor_id = await _sole_pending_competitor(api, owner, project_id)

        # Pending: in the queue, NOT in the approved feed.
        assert (await _approved(api, owner, project_id, competitor_id)) == []

        approved = await _approve(api, owner, project_id, observation_id)
        assert approved.status_code == 200, approved.text
        assert approved.json()["approval_state"] == "approved"

        queue = await api.get(
            f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
        )
        assert queue.json() == []
        feed = await _approved(api, owner, project_id, competitor_id)
        assert [o["id"] for o in feed] == [observation_id]

    async def test_new_value_supersedes_prior_approved(
        self, api, drain, extract_drain, owner, org, settings
    ):
        project_id = await new_project(api, owner, org)
        first_id = await _propose_price(
            api, drain, extract_drain, owner, project_id, PAGE_V1, "88"
        )
        competitor_id = await _sole_pending_competitor(api, owner, project_id)
        await _approve(api, owner, project_id, first_id)

        # A later snapshot shows a new price: proposed, approved, and
        # the prior approved row is superseded (never overwritten).
        second_id = await _propose_price(
            api, drain, extract_drain, owner, project_id, PAGE_V2, "95"
        )
        await _approve(api, owner, project_id, second_id)

        feed = await _approved(api, owner, project_id, competitor_id)
        assert [o["id"] for o in feed] == [second_id]

        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            row = await conn.fetchrow(
                "select approval_state, superseded_by from competitor.observations"
                " where id = $1",
                first_id,
            )
        finally:
            await conn.close()
        assert row["approval_state"] == "superseded"
        assert str(row["superseded_by"]) == second_id

    async def test_reject_retains_row_and_blocks_approval(
        self, api, drain, extract_drain, owner, org, settings
    ):
        project_id = await new_project(api, owner, org)
        observation_id = await _propose_price(
            api, drain, extract_drain, owner, project_id, PAGE_V1, "88"
        )
        competitor_id = await _sole_pending_competitor(api, owner, project_id)

        rejected = await _reject(api, owner, project_id, observation_id)
        assert rejected.status_code == 200, rejected.text

        # Retained for audit, out of both the queue and the feed.
        queue = await api.get(
            f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
        )
        assert queue.json() == []
        assert (await _approved(api, owner, project_id, competitor_id)) == []
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            row = await conn.fetchrow(
                "select approval_state from competitor.observations where id = $1",
                observation_id,
            )
        finally:
            await conn.close()
        assert row["approval_state"] == "rejected"

        # The state machine is strict: rejected rows can never flip.
        conflict = await _approve(api, owner, project_id, observation_id)
        assert conflict.status_code == 409

    async def test_double_approve_conflicts(self, api, drain, extract_drain, owner, org):
        project_id = await new_project(api, owner, org)
        observation_id = await _propose_price(
            api, drain, extract_drain, owner, project_id, PAGE_V1, "88"
        )
        first = await _approve(api, owner, project_id, observation_id)
        assert first.status_code == 200
        second = await _approve(api, owner, project_id, observation_id)
        assert second.status_code == 409

    async def test_viewer_reads_queue_but_cannot_review(
        self, api, drain, extract_drain, owner, viewer, org
    ):
        project_id = await new_project(api, owner, org)
        observation_id = await _propose_price(
            api, drain, extract_drain, owner, project_id, PAGE_V1, "88"
        )
        await _invite_viewer(api, owner, org, viewer, project_id)

        queue = await api.get(
            f"/projects/{project_id}/review-queue", headers=auth_headers(viewer)
        )
        assert queue.status_code == 200
        assert len(queue.json()) == 1

        denied = await _approve(api, viewer, project_id, observation_id)
        assert denied.status_code == 403
        denied_reject = await _reject(api, viewer, project_id, observation_id)
        assert denied_reject.status_code == 403
