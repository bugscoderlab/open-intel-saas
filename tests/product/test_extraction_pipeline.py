"""Managed HTTP seam: snapshot → proposed observations pipeline
(ticket #50, spec #47, Phase 5 2/3).

Extraction enqueue (202 + outbox event, one transaction) and the
off-request drain (ADR-004) run against the real app with a scripted
FakeExtractor — no network. The sink and snapshot source are the real
test adapters over the same managed database, so pending Observations,
snapshot EvidenceLinks, and audit rows are asserted in SQL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.extraction.application.services.extract_service import (
    drain_pending_extractions,
)
from modules.extraction.domain.entities import (
    EXTRACTION_VERSION,
    ExtractedItem,
    ExtractionResult,
)
from modules.extraction.domain.errors import ExtractionValidationError
from modules.extraction.infrastructure.unit_of_work import SqlExtractionUnit
from modules.platform.infrastructure.db import create_engine
from tests.product.conftest import TestUser, auth_headers
from tests.product.extraction_helpers import TestObservationSink, TestSnapshotSource
from tests.product.fakes import FakeExtractor, FakeWebsiteFetcher
from tests.product.research_helpers import new_project

PAGE = "<html><body>Full grooming RM88, first visit 10% off</body></html>"
URL = "https://paws.example.com/pricing"

RESULT = ExtractionResult(
    items=(
        ExtractedItem(
            kind="price",
            claim="Full grooming — RM88",
            price_amount=Decimal("88"),
            price_currency="MYR",
            confidence=Decimal("0.95"),
            excerpt="Full grooming RM88",
        ),
        ExtractedItem(
            kind="promotion",
            claim="10% off first visit",
            confidence=Decimal("0.8"),
            excerpt="first visit 10% off",
        ),
        ExtractedItem(
            kind="review_topic",
            claim="Gentle handling",
            sentiment="positive",
            confidence=Decimal("0.85"),
            excerpt="gentle with anxious dogs",
        ),
    )
)


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("extraction-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("extraction-viewer")


@pytest_asyncio.fixture
async def extract_drain(
    settings,
) -> AsyncIterator[Callable[[FakeExtractor], Awaitable[int]]]:
    """One extraction drain tick on a test-local engine bound to this
    test's event loop (same pattern as the collection `drain`)."""
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


async def _collect_snapshot(api, drain, owner: TestUser, project_id: str) -> tuple[str, str]:
    """On-demand collect a page; return (competitor_id, snapshot_id)."""
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
    await drain(FakeWebsiteFetcher(pages={URL: PAGE}))
    listing = await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
        headers=auth_headers(owner),
    )
    snapshots = listing.json()
    assert len(snapshots) == 1
    return competitor_id, snapshots[0]["id"]


async def _extract(api, user, project_id, competitor_id, snapshot_id):
    return await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}"
        f"/snapshots/{snapshot_id}/extract",
        headers=auth_headers(user),
    )


async def _db_counts(settings, project_id: str) -> tuple[list[dict], list[dict]]:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg)
    try:
        observations = [
            dict(row)
            for row in await conn.fetch(
                "select kind, approval_state, confidence, extraction_version"
                " from competitor.observations where project_id = $1"
                " order by kind",
                project_id,
            )
        ]
        evidence = [
            dict(row)
            for row in await conn.fetch(
                "select target_kind, approval_state, excerpt"
                " from competitor.evidence_links where project_id = $1"
                " order by excerpt",
                project_id,
            )
        ]
        return observations, evidence
    finally:
        await conn.close()


class TestExtractionPipeline:
    async def test_extract_enqueues_and_drain_records_proposed_observations(
        self, api, drain, extract_drain, owner, org, settings
    ):
        project_id = await new_project(api, owner, org)
        competitor_id, snapshot_id = await _collect_snapshot(
            api, drain, owner, project_id
        )

        queued = await _extract(api, owner, project_id, competitor_id, snapshot_id)
        assert queued.status_code == 202, queued.text
        run = queued.json()
        assert run["status"] == "pending"
        assert run["extraction_version"] == EXTRACTION_VERSION

        processed = await extract_drain(FakeExtractor(results={PAGE: RESULT}))
        assert processed == 1

        observations, evidence = await _db_counts(settings, project_id)
        assert [(o["kind"], o["approval_state"]) for o in observations] == [
            ("price", "pending"),
            ("promotion", "pending"),
            ("review_topic", "pending"),
        ]
        price = next(o for o in observations if o["kind"] == "price")
        assert abs(Decimal(price["confidence"]) - Decimal("0.95")) < Decimal("0.001")
        assert price["extraction_version"] == EXTRACTION_VERSION

        # Every proposed fact carries an evidence link to the snapshot.
        assert len(evidence) == 3
        assert all(row["target_kind"] == "snapshot" for row in evidence)
        assert sorted(row["excerpt"] for row in evidence) == [
            "Full grooming RM88",
            "first visit 10% off",
            "gentle with anxious dogs",
        ]

        # The proposed facts surface in the human review queue (spec #47:
        # separation of proposed from approved — everything here is
        # pending until an editor decides, ticket #51's seam).
        queue = await api.get(
            f"/projects/{project_id}/review-queue", headers=auth_headers(owner)
        )
        assert queue.status_code == 200, queue.text
        assert len(queue.json()) == 3

        # Audit trail: request → batch propose → succeeded.
        org_row = await api.get(f"/organizations/{org}", headers=auth_headers(owner))
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            actions = [
                row["action"]
                for row in await conn.fetch(
                    "select action from public.audit_log"
                    " where organization_id = $1 and action like 'extraction.%'",
                    org_row.json()["id"],
                )
            ]
        finally:
            await conn.close()
        assert "extraction.request" in actions
        assert "extraction.succeeded" in actions

    async def test_reenqueue_is_idempotent_per_snapshot_and_version(
        self, api, drain, extract_drain, owner, org, settings
    ):
        project_id = await new_project(api, owner, org)
        competitor_id, snapshot_id = await _collect_snapshot(
            api, drain, owner, project_id
        )

        first = await _extract(api, owner, project_id, competitor_id, snapshot_id)
        assert first.status_code == 202
        second = await _extract(api, owner, project_id, competitor_id, snapshot_id)
        assert second.status_code == 202
        assert second.json()["id"] == first.json()["id"]

        processed = await extract_drain(FakeExtractor(results={PAGE: RESULT}))
        assert processed == 1
        observations, _ = await _db_counts(settings, project_id)
        assert len(observations) == 3  # one drain, no duplicates

    async def test_viewer_cannot_enqueue_extraction(
        self, api, drain, owner, viewer, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id, snapshot_id = await _collect_snapshot(
            api, drain, owner, project_id
        )
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

        denied = await _extract(api, viewer, project_id, competitor_id, snapshot_id)
        assert denied.status_code == 403

    async def test_failed_run_records_error_and_retry_succeeds(
        self, api, drain, extract_drain, owner, org, settings
    ):
        project_id = await new_project(api, owner, org)
        competitor_id, snapshot_id = await _collect_snapshot(
            api, drain, owner, project_id
        )

        queued = await _extract(api, owner, project_id, competitor_id, snapshot_id)
        assert queued.status_code == 202
        first_run_id = queued.json()["id"]

        failing = FakeExtractor(results={PAGE: RESULT})
        failing.fail_with = ExtractionValidationError("model output is not valid JSON")
        processed = await extract_drain(failing)
        assert processed == 1

        # The failure is recorded with the typed error; the snapshot and
        # any previously proposed facts are untouched.
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            row = await conn.fetchrow(
                "select id, status, error from extraction.extraction_runs"
                " where snapshot_id = $1",
                snapshot_id,
            )
        finally:
            await conn.close()
        assert str(row["id"]) == first_run_id
        assert row["status"] == "failed"
        assert "not valid JSON" in row["error"]
        observations, _ = await _db_counts(settings, project_id)
        assert observations == []

        # A failed run may be re-enqueued (retry): a NEW run is created
        # and the drain succeeds end to end.
        retried = await _extract(api, owner, project_id, competitor_id, snapshot_id)
        assert retried.status_code == 202
        assert retried.json()["id"] != first_run_id
        processed = await extract_drain(FakeExtractor(results={PAGE: RESULT}))
        assert processed == 1
        observations, _ = await _db_counts(settings, project_id)
        assert len(observations) == 3

    async def test_unknown_snapshot_is_a_404(self, api, drain, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id, _ = await _collect_snapshot(api, drain, owner, project_id)
        missing = await _extract(
            api, owner, project_id, competitor_id, str(uuid4())
        )
        assert missing.status_code == 404
