"""Managed HTTP seam: review topics + location comparisons
(ticket #56, spec #52, Phase 6 3/4).

Review topics are seeded through the REAL extraction pipeline so the
claim+sentiment columns (migration 0022) are exercised end to end;
location rows use the manual observation endpoint with an explicit
location scope. Everything lands via the approval queue before metrics
read it — pending rows never appear.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

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

PAGE = "<html><body>gentle with anxious dogs, but prices climbed</body></html>"
URL = "https://paws.example.com/reviews"

REVIEW_RESULT = ExtractionResult(
    items=(
        ExtractedItem(
            kind="review_topic",
            claim="Gentle handling",
            sentiment="positive",
            confidence=Decimal("0.9"),
            excerpt="gentle with anxious dogs",
        ),
        ExtractedItem(
            kind="review_topic",
            claim="Gentle handling",
            sentiment="positive",
            confidence=Decimal("0.8"),
            excerpt="gentle",
        ),
        ExtractedItem(
            kind="review_topic",
            claim="Price complaints",
            sentiment="negative",
            confidence=Decimal("0.85"),
            excerpt="prices climbed",
        ),
    )
)


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("topics-owner")


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


async def _collect_and_extract(api, drain, extract_drain, owner, project_id):
    response = await api.post(
        f"/projects/{project_id}/competitors",
        json={"name": "Paws"},
        headers=auth_headers(owner),
    )
    competitor_id = response.json()["id"]
    queued = await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/collections",
        json={"connector_kind": "website", "url": URL},
        headers=auth_headers(owner),
    )
    assert queued.status_code == 202, queued.text
    await drain(FakeWebsiteFetcher(pages={URL: PAGE}))
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
    await extract_drain(FakeExtractor(results={PAGE: REVIEW_RESULT}))
    return competitor_id


async def _approve_all_pending(api, owner, project_id):
    queue = await api.get(
        f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
    )
    for observation in queue.json():
        approved = await api.post(
            f"/projects/{project_id}/observations/{observation['id']}/approve",
            headers=auth_headers(owner),
        )
        assert approved.status_code == 200, approved.text


class TestReviewTopics:
    async def test_topics_aggregate_mentions_and_dominant_sentiment(
        self, api, drain, extract_drain, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _collect_and_extract(
            api, drain, extract_drain, owner, project_id
        )
        await _approve_all_pending(api, owner, project_id)

        response = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}"
            "/analytics/review-topics",
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["metric"] == "review_topics"
        topics = {p["topic"]: p for p in payload["points"]}
        assert topics["Gentle handling"]["mentions"] == 2
        assert topics["Gentle handling"]["dominant_sentiment"] == "positive"
        assert topics["Price complaints"]["mentions"] == 1
        assert topics["Price complaints"]["dominant_sentiment"] == "negative"

    async def test_pending_topics_do_not_appear(self, api, drain, extract_drain, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await _collect_and_extract(
            api, drain, extract_drain, owner, project_id
        )
        response = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}"
            "/analytics/review-topics",
            headers=auth_headers(owner),
        )
        assert response.status_code == 200
        assert response.json()["points"] == []

    async def test_sentiment_tie_reports_mixed(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await api.post(
            f"/projects/{project_id}/competitors",
            json={"name": "Paws"},
            headers=auth_headers(owner),
        )
        competitor_id = competitor_id.json()["id"]
        # One positive + one negative mention of the same topic: the
        # dominant sentiment is a tie -> 'mixed'.
        for sentiment in ("positive", "negative"):
            await _propose_review_topic(
                owner, project_id, competitor_id, sentiment
            )
        await _approve_all_pending(api, owner, project_id)
        response = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}"
            "/analytics/review-topics",
            headers=auth_headers(owner),
        )
        topics = {p["topic"]: p for p in response.json()["points"]}
        assert topics["Mixed feelings"]["dominant_sentiment"] == "mixed"


async def _propose_review_topic(
    owner: TestUser, project_id: str, competitor_id: str, sentiment: str
) -> None:
    """Direct DB insert of a proposed review topic — the manual endpoint
    only creates price rows, so sentiment coverage uses raw inserts
    scoped to this test's project."""
    import asyncpg

    from modules.platform.infrastructure.settings import Settings

    config = Settings.from_env()
    conn = await asyncpg.connect(config.database_dsn_asyncpg)
    try:
        project = await conn.fetchrow(
            "select organization_id from public.projects where id = $1", project_id
        )
        app_user = await conn.fetchrow(
            "select id from public.app_users where email = $1", owner.email
        )
        assert app_user is not None
        await conn.execute(
            "insert into competitor.observations"
            " (id, organization_id, project_id, competitor_id, service_id,"
            "  location_id, kind, price_amount, price_currency, observed_on,"
            "  confidence, extraction_version, approval_state, superseded_by,"
            "  created_by, claim, sentiment)"
            " values (gen_random_uuid(), $1, $2, $3, NULL, NULL, 'review_topic',"
            "  NULL, NULL, '2026-09-10', 0.9, 'test-v1', 'pending', NULL,"
            "  $4, 'Mixed feelings', $5)",
            project["organization_id"],
            project_id,
            competitor_id,
            app_user["id"],
            sentiment,
        )
    finally:
        await conn.close()


class TestLocationComparison:
    async def test_groups_by_location_with_market_rollup(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await api.post(
            f"/projects/{project_id}/competitors",
            json={"name": "Paws"},
            headers=auth_headers(owner),
        )
        competitor_id = competitor_id.json()["id"]
        branch = await api.post(
            f"/projects/{project_id}/competitors/{competitor_id}/locations",
            json={"name": "Downtown", "address": "1 Main St"},
            headers=auth_headers(owner),
        )
        assert branch.status_code == 201, branch.text
        branch_id = branch.json()["id"]

        # One market-level price, one branch-level price.
        for location_id, amount in ((None, "88"), (branch_id, "95")):
            body = {
                "kind": "price",
                "price_amount": amount,
                "price_currency": "MYR",
                "observed_on": "2026-09-01",
            }
            if location_id is not None:
                body["location_id"] = location_id
            proposed = await api.post(
                f"/projects/{project_id}/competitors/{competitor_id}/observations",
                json=body,
                headers=auth_headers(owner),
            )
            assert proposed.status_code == 201, proposed.text
            await api.post(
                f"/projects/{project_id}/observations/{proposed.json()['id']}/approve",
                headers=auth_headers(owner),
            )

        response = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/analytics/locations",
            headers=auth_headers(owner),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["metric"] == "location_comparison"
        points = payload["points"]
        assert len(points) == 2
        by_location = {p["location_id"]: p for p in points}
        assert by_location[None]["location_name"] is None  # market roll-up
        assert by_location[None]["latest_price_amount"] == "88.00"
        assert by_location[branch_id]["location_name"] == "Downtown"
        assert by_location[branch_id]["latest_price_amount"] == "95.00"
        assert all(p["kind"] == "price" for p in points)
        assert all(p["count"] == 1 for p in points)
