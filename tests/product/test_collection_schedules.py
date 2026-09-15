"""HTTP seam: scheduled collection (ticket #44, spec #41, Phase 4 3/3).

Schedules are editor-managed (collection.job.manage); the scheduler
claims due jobs through CollectionDue outbox events (ADR-004) and the
SAME drain pipeline as on-demand runs. Clock: real UTC; tests use one
second intervals (recorded choice on the ticket — no fake clock).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.collection.application.services.collect_service import (
    drain_pending_runs,
)
from modules.collection.infrastructure.unit_of_work import SqlCollectionUnit
from modules.platform.infrastructure.db import create_engine
from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import FakeWebsiteFetcher
from tests.product.research_helpers import new_project

URL = "https://paws.example.com/pricing"
PRICING_PAGE = "<html><body>Full groom $45</body></html>"


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("schedule-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("schedule-viewer")


@pytest_asyncio.fixture
async def scheduler(
    settings,
) -> AsyncIterator[
    Callable[[FakeWebsiteFetcher], Awaitable[tuple[int, list[str]]]]
]:
    """One scheduler tick (claim due schedules) + drain, on a test-local
    engine bound to this test's event loop (same pattern as `drain`).
    Returns (claimed_count, fetched_urls) so tests can assert on the
    outbox behavior, not just side effects."""

    from modules.collection.infrastructure.dispatcher import run_scheduler_tick

    engine = create_engine(settings.database_dsn)

    async def _tick(fetcher: FakeWebsiteFetcher) -> tuple[int, list[str]]:
        claimed = await run_scheduler_tick(lambda: SqlCollectionUnit(engine))
        await drain_pending_runs(lambda: SqlCollectionUnit(engine), fetcher)
        return claimed, list(fetcher.fetched)

    yield _tick
    await engine.dispose()


async def _new_competitor(api, owner: TestUser, project_id: str, name: str = "Paws") -> str:
    response = await api.post(
        f"/projects/{project_id}/competitors",
        json={"name": name},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_job(
    api, user: TestUser, project_id: str, competitor_id: str, interval: int = 3600,
    url: str = URL,
):
    return await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/jobs",
        json={"connector_kind": "website", "url": url, "interval_seconds": interval},
        headers=auth_headers(user),
    )


async def _jobs(api, user: TestUser, project_id: str, competitor_id: str):
    return await api.get(
        f"/projects/{project_id}/competitors/{competitor_id}/jobs",
        headers=auth_headers(user),
    )


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


class TestJobManagement:
    async def test_create_list_delete_job_with_audit(self, api, settings, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id)

        created = await _create_job(api, owner, project_id, competitor_id)
        assert created.status_code == 201, created.text
        job = created.json()
        assert job["url"] == URL
        assert job["interval_seconds"] == 3600
        assert job["enabled"] is True
        assert job["failures"] == 0
        assert "next_due_at" in job

        listed = await _jobs(api, owner, project_id, competitor_id)
        assert [j["id"] for j in listed.json()] == [job["id"]]

        deleted = await api.delete(
            f"/projects/{project_id}/competitors/{competitor_id}/jobs/{job['id']}",
            headers=auth_headers(owner),
        )
        assert deleted.status_code == 204
        assert (await _jobs(api, owner, project_id, competitor_id)).json() == []

        org_row = await api.get(f"/organizations/{org}", headers=auth_headers(owner))
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            actions = [
                row["action"]
                for row in await conn.fetch(
                    "select action from public.audit_log"
                    " where organization_id = $1 and action like 'collection.job.%'",
                    org_row.json()["id"],
                )
            ]
        finally:
            await conn.close()
        assert "collection.job.create" in actions
        assert "collection.job.delete" in actions

    async def test_viewer_cannot_manage_jobs(self, api, owner, viewer, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id)
        await _invite_project_viewer(api, owner, org, viewer, project_id)

        assert (await _create_job(api, viewer, project_id, competitor_id)).status_code == 403
        await _create_job(api, owner, project_id, competitor_id)
        assert (await _jobs(api, viewer, project_id, competitor_id)).status_code == 403


class TestScheduler:
    async def test_due_job_claimed_and_produces_snapshot(self, api, scheduler, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id)
        job = (
            await _create_job(api, owner, project_id, competitor_id, interval=2)
        ).json()

        # The first run is due one interval from creation: not claimable
        # immediately after create.
        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 0
        assert fetched == []

        # Once the interval elapses, the tick claims it through the
        # CollectionDue outbox event and the drain snapshots it.
        await asyncio.sleep(2.2)  # real clock, short interval (recorded choice)
        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 1
        assert fetched == [URL]

        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert len(listing.json()) == 1

        # The cadence repeats: after the interval elapses the schedule is
        # due again — same content, so the run is recorded as unchanged
        # and no second snapshot appears (dedup, spec #41 acceptance 6).
        await asyncio.sleep(2.2)
        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 1
        assert fetched == [URL]

        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert len(listing.json()) == 1
        runs = (
            await api.get(
                f"/projects/{project_id}/competitors/{competitor_id}/jobs/{job['id']}/runs",
                headers=auth_headers(owner),
            )
        ).json()
        assert {r["status"] for r in runs} == {"snapshot_created", "unchanged"}

        # Forced ad-hoc run on a fresh long-interval schedule (the short
        # cadence schedule is deleted first — managed-DB latency between
        # ticks is seconds, so an interval-2 schedule cannot survive HTTP
        # round trips without becoming due again; that race is the real
        # clock's, not the scheduler's). Same URL: the forced run dedups
        # against the existing snapshot.
        deleted = await api.delete(
            f"/projects/{project_id}/competitors/{competitor_id}/jobs/{job['id']}",
            headers=auth_headers(owner),
        )
        assert deleted.status_code == 204
        long_job = (
            await _create_job(api, owner, project_id, competitor_id, interval=300)
        ).json()
        forced = await api.post(
            f"/projects/{project_id}/competitors/{competitor_id}/jobs/{long_job['id']}/run",
            headers=auth_headers(owner),
        )
        assert forced.status_code == 202, forced.text
        _, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert fetched == [URL]
        runs = (
            await api.get(
                f"/projects/{project_id}/competitors/{competitor_id}/jobs/{long_job['id']}/runs",
                headers=auth_headers(owner),
            )
        ).json()
        assert [r["status"] for r in runs] == ["unchanged"]
        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert len(listing.json()) == 1

    async def test_never_double_claims_while_not_due(
        self, api, scheduler, owner, org
    ):
        # ADR-004 with a long interval (no clock race): a schedule that
        # is not due is never claimed — before OR after a forced run.
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id)
        job = (
            await _create_job(api, owner, project_id, competitor_id, interval=300)
        ).json()

        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 0
        assert fetched == []

        forced = await api.post(
            f"/projects/{project_id}/competitors/{competitor_id}/jobs/{job['id']}/run",
            headers=auth_headers(owner),
        )
        assert forced.status_code == 202, forced.text
        _, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert fetched == [URL]

        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 0
        assert fetched == []

    async def test_failed_run_backs_off_and_never_stalls_the_queue(
        self, api, scheduler, owner, org
    ):
        # Failure isolation within a drain tick is proven in #42's drain
        # tests; here the schedule-level story: a failed run is recorded,
        # the schedule backs off instead of retrying at its plain
        # interval, and a forced successful run resets the streak.
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id)
        failing_job = (
            await _create_job(api, owner, project_id, competitor_id, interval=1)
        ).json()

        await asyncio.sleep(1.2)
        from modules.collection.domain.errors import FetchFailedError

        bad = FakeWebsiteFetcher({URL: PRICING_PAGE})
        bad.fail_with = FetchFailedError("connection reset")
        claimed, _ = await scheduler(bad)
        assert claimed == 1

        good_listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert good_listing.json() == []

        # Backoff state: failures incremented, next due ~60s out, not 1s.
        jobs = (await _jobs(api, owner, project_id, competitor_id)).json()
        assert jobs[0]["failures"] == 1
        next_due = datetime.fromisoformat(jobs[0]["next_due_at"])
        seconds = (next_due - datetime.now(UTC)).total_seconds()
        assert 50 < seconds <= 3600

        # Backoff dominates the plain interval: waiting another full
        # interval does NOT re-claim the schedule.
        await asyncio.sleep(1.2)
        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 0
        assert fetched == []

        # The failed run is listable with its typed error.
        runs = (
            await api.get(
                f"/projects/{project_id}/competitors/{competitor_id}/jobs/{failing_job['id']}/runs",
                headers=auth_headers(owner),
            )
        ).json()
        assert runs[0]["status"] == "failed"
        assert "connection reset" in runs[0]["error"]
        assert runs[0]["attempt"] == 0

        # Force a successful run: the schedule resets and resumes its
        # plain interval cadence.
        await api.post(
            f"/projects/{project_id}/competitors/{competitor_id}/jobs/{failing_job['id']}/run",
            headers=auth_headers(owner),
        )
        _, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert fetched == [URL]
        jobs = (await _jobs(api, owner, project_id, competitor_id)).json()
        assert jobs[0]["failures"] == 0

    async def test_deleting_a_job_stops_future_runs(self, api, scheduler, owner, org):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id)
        job = (await _create_job(api, owner, project_id, competitor_id, interval=1)).json()

        await api.delete(
            f"/projects/{project_id}/competitors/{competitor_id}/jobs/{job['id']}",
            headers=auth_headers(owner),
        )
        await asyncio.sleep(1.2)
        claimed, fetched = await scheduler(FakeWebsiteFetcher({URL: PRICING_PAGE}))
        assert claimed == 0
        assert fetched == []
        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert listing.json() == []
