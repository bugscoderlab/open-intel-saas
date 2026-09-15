"""HTTP seam + adapter tests: on-demand website collection (ticket #42,
spec #41, Phase 4 1/3).

The seam half drives the real API + managed project: an editor POSTs a
collection (202, job pending), the drain runs the FakeWebsiteFetcher
off-request (ADR-004 — the same drain the production dispatcher loops),
and snapshots land sha256-deduped. The adapter half unit-tests the
reference httpx fetcher's SSRF rules with a mocked transport and a
stubbed DNS resolver — no network anywhere.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC

import asyncpg
import httpx
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.collection.application.services.collect_service import drain_pending_jobs
from modules.collection.domain.errors import (
    FetchFailedError,
    FetchTargetNotAllowedError,
)
from modules.collection.infrastructure.http_fetcher import HttpxWebsiteFetcher
from modules.collection.infrastructure.unit_of_work import SqlCollectionUnit
from modules.platform.infrastructure.db import create_engine
from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import FakeWebsiteFetcher
from tests.product.research_helpers import new_project

PRICING_PAGE = "<html><body>Full groom $45</body></html>"
PRICING_PAGE_V2 = "<html><body>Full groom $49</body></html>"


@pytest_asyncio.fixture
async def drain(settings) -> AsyncIterator[Callable[[FakeWebsiteFetcher], Awaitable[int]]]:
    """Run the collection drain on demand, on a test-local engine that
    dies with the test's event loop (mirrors the research drain fixture;
    the session-scoped conftest engine's pooled connections bind to the
    first loop that touched them)."""
    engine = create_engine(settings.database_dsn)

    async def _drain(fetcher: FakeWebsiteFetcher) -> int:
        return await drain_pending_jobs(lambda: SqlCollectionUnit(engine), fetcher)

    yield _drain
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("collection-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("collection-viewer")


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


async def _new_competitor(api, owner: TestUser, project_id: str, name: str) -> str:
    response = await api.post(
        f"/projects/{project_id}/competitors",
        json={"name": name},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _request_collection(
    api, user: TestUser, project_id: str, competitor_id: str, url: str
):
    return await api.post(
        f"/projects/{project_id}/competitors/{competitor_id}/collections",
        json={"connector_kind": "website", "url": url},
        headers=auth_headers(user),
    )


async def _audit_actions(settings, organization_id: str) -> list[str]:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg)
    try:
        rows = await conn.fetch(
            "select action from public.audit_log where organization_id = $1",
            organization_id,
        )
        return [row["action"] for row in rows]
    finally:
        await conn.close()


class TestOnDemandCollection:
    async def test_collect_creates_snapshot_after_drain(
        self, api, drain, settings, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        url = "https://paws.example.com/pricing"

        response = await _request_collection(api, owner, project_id, competitor_id, url)
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["status"] == "pending"
        assert job["competitor_id"] == competitor_id
        assert job["connector_kind"] == "website"

        fetcher = FakeWebsiteFetcher(pages={url: PRICING_PAGE})
        assert await drain(fetcher) == 1
        assert fetcher.fetched == [url]

        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert listing.status_code == 200, listing.text
        snapshots = listing.json()
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot["competitor_id"] == competitor_id
        assert snapshot["connector_kind"] == "website"
        assert snapshot["url"] == url
        assert len(snapshot["content_hash"]) == 64
        assert "captured_at" in snapshot

        detail = await api.get(
            f"/projects/{project_id}/snapshots/{snapshot['id']}",
            headers=auth_headers(owner),
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["raw_payload"] == PRICING_PAGE

    async def test_unchanged_content_writes_no_new_snapshot(
        self, api, drain, settings, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        url = "https://paws.example.com/pricing"
        fetcher = FakeWebsiteFetcher(pages={url: PRICING_PAGE})

        first = await _request_collection(api, owner, project_id, competitor_id, url)
        assert first.status_code == 202
        await drain(fetcher)

        second = await _request_collection(api, owner, project_id, competitor_id, url)
        assert second.status_code == 202
        await drain(fetcher)

        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert len(listing.json()) == 1

        # Both runs recorded on the job rows: created, then unchanged.
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            rows = await conn.fetch(
                "select status from collection.jobs where project_id = $1"
                " order by created_at",
                project_id,
            )
        finally:
            await conn.close()
        assert [row["status"] for row in rows] == ["snapshot_created", "unchanged"]

    async def test_changed_content_appends_and_retains_old_snapshots(
        self, api, drain, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        url = "https://paws.example.com/pricing"

        fetcher = FakeWebsiteFetcher(pages={url: PRICING_PAGE})
        await _request_collection(api, owner, project_id, competitor_id, url)
        await drain(fetcher)

        fetcher.pages[url] = PRICING_PAGE_V2
        await _request_collection(api, owner, project_id, competitor_id, url)
        await drain(fetcher)

        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        snapshots = listing.json()
        assert len(snapshots) == 2
        # Newest first; both payloads retained.
        assert snapshots[0]["captured_at"] >= snapshots[1]["captured_at"]
        detail_new = await api.get(
            f"/projects/{project_id}/snapshots/{snapshots[0]['id']}",
            headers=auth_headers(owner),
        )
        detail_old = await api.get(
            f"/projects/{project_id}/snapshots/{snapshots[1]['id']}",
            headers=auth_headers(owner),
        )
        assert {detail_new.json()["raw_payload"], detail_old.json()["raw_payload"]} == {
            PRICING_PAGE,
            PRICING_PAGE_V2,
        }

    async def test_failed_fetch_records_job_and_keeps_last_snapshot(
        self, api, drain, settings, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        url = "https://paws.example.com/pricing"

        good = FakeWebsiteFetcher(pages={url: PRICING_PAGE})
        await _request_collection(api, owner, project_id, competitor_id, url)
        await drain(good)

        bad = FakeWebsiteFetcher()
        bad.fail_with = FetchFailedError("connection reset")
        failing = await _request_collection(api, owner, project_id, competitor_id, url)
        assert failing.status_code == 202
        await drain(bad)

        # The previous successful snapshot is still there.
        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert len(listing.json()) == 1

        # The failed run is recorded with its typed error on the job row.
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            rows = await conn.fetch(
                "select status, error from collection.jobs"
                " where project_id = $1 order by created_at",
                project_id,
            )
        finally:
            await conn.close()
        assert [(row["status"], row["error"]) for row in rows] == [
            ("snapshot_created", None),
            ("failed", "connection reset"),
        ]

        org_row = await api.get(f"/organizations/{org}", headers=auth_headers(owner))
        actions = await _audit_actions(settings, org_row.json()["id"])
        assert "collection.failed" in actions
        assert "collection.snapshot_created" in actions

    async def test_viewer_reads_snapshots_but_cannot_collect(
        self, api, drain, owner, viewer, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        await _invite_project_viewer(api, owner, org, viewer, project_id)
        url = "https://paws.example.com/pricing"

        denied = await _request_collection(api, viewer, project_id, competitor_id, url)
        assert denied.status_code == 403

        await _request_collection(api, owner, project_id, competitor_id, url)
        await drain(FakeWebsiteFetcher({url: PRICING_PAGE}))
        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(viewer),
        )
        assert listing.status_code == 200, listing.text
        assert len(listing.json()) == 1

    async def test_per_project_fetch_quota_is_enforced(
        self, api, drain, owner, org
    ):
        project_id = await new_project(api, owner, org)
        competitor_id = await _new_competitor(api, owner, project_id, "Paws")
        api.app.state.collection_quota = 1
        try:
            first = await _request_collection(
                api, owner, project_id, competitor_id, "https://paws.example.com/a"
            )
            assert first.status_code == 202
            second = await _request_collection(
                api, owner, project_id, competitor_id, "https://paws.example.com/b"
            )
            assert second.status_code == 409, second.text
        finally:
            api.app.state.collection_quota = None


class _StubResolver:
    """Records every hostname it is asked about and answers canned IPs."""

    def __init__(self, addresses: list[str]) -> None:
        self.addresses = addresses
        self.asked: list[str] = []

    async def __call__(self, hostname: str) -> list[str]:
        self.asked.append(hostname)
        return list(self.addresses)


def _mocked_fetcher(handler, resolver: _StubResolver) -> HttpxWebsiteFetcher:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://fetcher.test"
    )
    return HttpxWebsiteFetcher(client, resolver=resolver)


class TestFetcherSsrfGuards:
    async def test_refuses_private_literal_host(self):
        resolver = _StubResolver(["93.184.216.34"])
        fetcher = _mocked_fetcher(
            lambda request: httpx.Response(200, text="ok"), resolver
        )
        with pytest.raises(FetchTargetNotAllowedError):
            await fetcher.fetch("http://10.0.0.7/admin")
        with pytest.raises(FetchTargetNotAllowedError):
            await fetcher.fetch("http://127.0.0.1:5055/health")
        with pytest.raises(FetchTargetNotAllowedError):
            await fetcher.fetch("http://169.254.169.254/latest/meta-data")

    async def test_refuses_when_dns_resolves_non_public(self):
        resolver = _StubResolver(["10.1.2.3"])
        fetcher = _mocked_fetcher(
            lambda request: httpx.Response(200, text="ok"), resolver
        )
        with pytest.raises(FetchTargetNotAllowedError):
            await fetcher.fetch("http://intranet.example.com/page")
        # The hostname was resolved and rejected before any request.
        assert resolver.asked == ["intranet.example.com"]

    async def test_redirect_to_private_host_is_refused_and_dns_revalidated(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "public.example.com":
                return httpx.Response(
                    302, headers={"location": "http://vault.local:8080/secret"}
                )
            return httpx.Response(200, text="should never be served")

        # First hop resolves public, redirect target resolves private:
        # the rebinding-style smuggle must be caught per hop.
        asked: list[str] = []

        async def resolver(hostname: str) -> list[str]:
            asked.append(hostname)
            return ["93.184.216.34"] if hostname == "public.example.com" else ["192.168.0.9"]

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://fetcher.test"
        )
        fetcher = HttpxWebsiteFetcher(client, resolver=resolver)
        with pytest.raises(FetchTargetNotAllowedError):
            await fetcher.fetch("http://public.example.com/start")
        # DNS was revalidated for the redirect hop too.
        assert asked == ["public.example.com", "vault.local"]

    async def test_happy_path_returns_fetched_page(self):
        resolver = _StubResolver(["93.184.216.34"])
        fetcher = _mocked_fetcher(
            lambda request: httpx.Response(200, text=PRICING_PAGE), resolver
        )
        page = await fetcher.fetch("https://paws.example.com/pricing")
        assert page.status_code == 200
        assert page.content == PRICING_PAGE
        assert page.url == "https://paws.example.com/pricing"
        assert page.fetched_at.tzinfo == UTC

    async def test_http_error_status_is_typed_failure(self):
        resolver = _StubResolver(["93.184.216.34"])
        fetcher = _mocked_fetcher(
            lambda request: httpx.Response(500, text="boom"), resolver
        )
        with pytest.raises(FetchFailedError):
            await fetcher.fetch("https://paws.example.com/pricing")
