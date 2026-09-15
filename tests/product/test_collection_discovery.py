"""HTTP seam: maps discovery (ticket #43, spec #41, Phase 4 2/3).

Discovery returns candidate businesses as DATA through the
FakeMapsProvider — nothing is persisted, adding a candidate stays the
Phase 3 manual competitor flow, and a failing maps provider never
affects website collection (independent connectors, user story 5). The
"not configured" policy is proven end-to-end with the REAL adapter and
an empty key (the embedder failure policy, ticket #24).
"""

from __future__ import annotations

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.collection.infrastructure.google_places import (
    GooglePlacesMapsProvider,
)
from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import FakeMapsProvider, FakeWebsiteFetcher
from tests.product.research_helpers import new_project

PRICING_PAGE = "<html><body>Full groom $45</body></html>"

PAWS_CANDIDATE = {
    "name": "Paws Grooming",
    "address": "12 Main St, Springfield",
    "website": "https://paws.example.com",
    "provider_metadata": {"provider": "google_places", "place_id": "ChIJpaws"},
}
CLAWS_CANDIDATE = {
    "name": "Claws & Co",
    "address": "9 Oak Ave, Springfield",
    "website": None,
    "provider_metadata": {"provider": "google_places", "place_id": "ChIJclaws"},
}


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("discovery-owner")


@pytest_asyncio.fixture
async def viewer(user_factory) -> TestUser:
    return await user_factory("discovery-viewer")


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


async def _discover(api, user: TestUser, project_id: str, query: str, location: str):
    return await api.post(
        f"/projects/{project_id}/discover",
        json={"query": query, "location": location},
        headers=auth_headers(user),
    )


class TestMapsDiscovery:
    async def test_discover_returns_candidates_as_data(self, api, owner, org):
        project_id = await new_project(api, owner, org)
        provider = api.app.state.collection_maps_provider
        provider.candidates[("pet grooming", "Springfield")] = [
            PAWS_CANDIDATE,
            CLAWS_CANDIDATE,
        ]

        response = await _discover(api, owner, project_id, "pet grooming", "Springfield")
        assert response.status_code == 200, response.text
        candidates = response.json()
        assert [c["name"] for c in candidates] == ["Paws Grooming", "Claws & Co"]
        paws = candidates[0]
        assert paws["address"] == "12 Main St, Springfield"
        assert paws["website"] == "https://paws.example.com"
        assert paws["provider_metadata"]["place_id"] == "ChIJpaws"
        assert provider.queries == [("pet grooming", "Springfield")]

    async def test_discover_persists_nothing(self, api, settings, owner, org):
        project_id = await new_project(api, owner, org)
        before = (
            await api.get(
                f"/projects/{project_id}/competitors", headers=auth_headers(owner)
            )
        ).json()
        provider = api.app.state.collection_maps_provider
        provider.candidates[("pet grooming", "Springfield")] = [PAWS_CANDIDATE]

        response = await _discover(api, owner, project_id, "pet grooming", "Springfield")
        assert response.status_code == 200

        after = (
            await api.get(
                f"/projects/{project_id}/competitors", headers=auth_headers(owner)
            )
        ).json()
        assert after == before == []
        # and no collection rows exist for this project either
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            snapshots = await conn.fetchval(
                "select count(*) from collection.snapshots where project_id = $1",
                project_id,
            )
            jobs = await conn.fetchval(
                "select count(*) from collection.job_runs where project_id = $1",
                project_id,
            )
        finally:
            await conn.close()
        assert snapshots == 0
        assert jobs == 0

    async def test_unconfigured_provider_fails_with_typed_error(
        self, api, owner, org
    ):
        """The REAL adapter with an empty key: misconfiguration is a
        visible typed 503, never silent (embedder failure policy)."""
        project_id = await new_project(api, owner, org)
        api.app.state.collection_maps_provider = GooglePlacesMapsProvider(api_key="")
        try:
            response = await _discover(
                api, owner, project_id, "pet grooming", "Springfield"
            )
            assert response.status_code == 503, response.text
            assert "not configured" in response.json()["detail"]
        finally:
            api.app.state.collection_maps_provider = FakeMapsProvider()

    async def test_failing_provider_does_not_affect_website_collection(
        self, api, drain, owner, org
    ):
        """Independent connectors (user story 5): a broken maps provider
        leaves on-demand website collection fully working."""
        project_id = await new_project(api, owner, org)
        competitor_id = (
            await api.post(
                f"/projects/{project_id}/competitors",
                json={"name": "Paws"},
                headers=auth_headers(owner),
            )
        ).json()["id"]
        provider = api.app.state.collection_maps_provider
        from modules.collection.domain.errors import MapsProviderError

        provider.fail_with = MapsProviderError("maps provider outage")

        failing = await _discover(api, owner, project_id, "pet grooming", "Springfield")
        assert failing.status_code == 503

        url = "https://paws.example.com/pricing"
        collect = await api.post(
            f"/projects/{project_id}/competitors/{competitor_id}/collections",
            json={"connector_kind": "website", "url": url},
            headers=auth_headers(owner),
        )
        assert collect.status_code == 202, collect.text
        await drain(FakeWebsiteFetcher({url: PRICING_PAGE}))
        listing = await api.get(
            f"/projects/{project_id}/competitors/{competitor_id}/snapshots",
            headers=auth_headers(owner),
        )
        assert len(listing.json()) == 1

    async def test_viewer_cannot_discover(self, api, owner, viewer, org):
        project_id = await new_project(api, owner, org)
        await _invite_project_viewer(api, owner, org, viewer, project_id)
        response = await _discover(api, viewer, project_id, "pet grooming", "Springfield")
        assert response.status_code == 403

    async def test_discover_writes_an_audit_row(self, api, settings, owner, org):
        project_id = await new_project(api, owner, org)
        provider = api.app.state.collection_maps_provider
        provider.candidates[("pet grooming", "Springfield")] = [PAWS_CANDIDATE]
        response = await _discover(api, owner, project_id, "pet grooming", "Springfield")
        assert response.status_code == 200

        org_row = await api.get(f"/organizations/{org}", headers=auth_headers(owner))
        conn = await asyncpg.connect(settings.database_dsn_asyncpg)
        try:
            rows = await conn.fetch(
                "select action, payload from public.audit_log"
                " where organization_id = $1 and action = 'collection.discover'",
                org_row.json()["id"],
            )
        finally:
            await conn.close()
        assert len(rows) == 1
        import json

        payload = json.loads(rows[0]["payload"])
        assert payload["query"] == "pet grooming"
        assert payload["location"] == "Springfield"
        assert payload["candidates"] == 1


class TestGooglePlacesAdapter:
    """Unit tests for the reference adapter over a mocked transport —
    the real Places API is ticket #45 (ready-for-human)."""

    def _client(self, handler):
        import httpx

        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://maps.test"
        )

    async def test_unconfigured_raises_typed_error(self):
        provider = GooglePlacesMapsProvider(api_key="")
        with pytest.raises(Exception) as excinfo:  # noqa: B017 (asserted below)
            await provider.discover(query="grooming", location="Springfield")
        assert excinfo.type.__name__ == "MapsConfigurationError"

    async def test_parses_candidates_from_text_search(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert "grooming in Springfield" in request.url.params["query"]
            assert request.url.params["key"] == "test-key"
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "results": [
                        {
                            "name": "Paws Grooming",
                            "formatted_address": "12 Main St, Springfield",
                            "place_id": "ChIJpaws",
                            "rating": 4.7,
                            "user_ratings_total": 53,
                            "types": ["pet_store", "point_of_interest"],
                        }
                    ],
                },
            )

        provider = GooglePlacesMapsProvider(
            api_key="test-key", client=self._client(handler)
        )
        candidates = await provider.discover(query="grooming", location="Springfield")
        assert len(candidates) == 1
        assert candidates[0].name == "Paws Grooming"
        assert candidates[0].website is None  # Text Search carries no website
        assert candidates[0].provider_metadata["place_id"] == "ChIJpaws"
        assert candidates[0].provider_metadata["rating"] == 4.7

    async def test_provider_error_status_is_typed(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "REQUEST_DENIED",
                    "error_message": "The provided API key is invalid.",
                },
            )

        provider = GooglePlacesMapsProvider(
            api_key="bad-key", client=self._client(handler)
        )
        with pytest.raises(Exception) as excinfo:  # noqa: B017 (asserted below)
            await provider.discover(query="grooming", location="Springfield")
        assert excinfo.type.__name__ == "MapsProviderError"
        assert "REQUEST_DENIED" in str(excinfo.value)
