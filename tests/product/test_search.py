"""HTTP seam: tenant-scoped text + vector search (ticket #25, spec #21).

Bullet 4/4 — completes the tracer bullet: notebook → source → processed
chunks + embeddings → searchable evidence. Authorization happens before
retrieval: the tenant scope is part of the query predicate, never a
post-filter. Vector search reuses the same fake-embedder seam as #24 —
no real provider calls anywhere in these tests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import KeywordEmbedder
from tests.product.research_helpers import (
    create_text_source,
    new_notebook,
    new_project,
)

GROOMING_TEXT = (
    "Full grooming, basic grooming, nail trim and ear cleaning. "
    "Full grooming prices went up again this quarter. " * 60
)
VET_TEXT = (
    "Veterinary appointments, vaccination schedules and deworming. "
    "The vet clinic opens at nine on weekdays. " * 60
)


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("search-owner")


@pytest_asyncio.fixture
async def project_with_sources(api, owner: TestUser, org: str, drain_with) -> dict:
    """Two processed sources (grooming + vet) and one still-queued source
    that also mentions grooming — the queued one must not appear in text
    search results."""
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    embedder = KeywordEmbedder("grooming", "veterinary")
    grooming = await create_text_source(
        api, owner, project_id, notebook_id, GROOMING_TEXT
    )
    vet = await create_text_source(api, owner, project_id, notebook_id, VET_TEXT)
    assert (await drain_with(embedder)) >= 1
    queued = await create_text_source(
        api, owner, project_id, notebook_id, "grooming gossip, unprocessed"
    )
    return {
        "project_id": project_id,
        "notebook_id": notebook_id,
        "embedder": embedder,
        "grooming_id": grooming["id"],
        "vet_id": vet["id"],
        "queued_id": queued["id"],
    }


async def test_text_search_ranks_project_sources(
    api, owner: TestUser, project_with_sources
) -> None:
    project_id = project_with_sources["project_id"]
    response = await api.get(
        f"/projects/{project_id}/search/text",
        params={"q": "grooming"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200, response.text
    hits = response.json()
    assert len(hits) >= 1
    # the processed grooming source ranks first; the queued one never shows
    assert hits[0]["source_id"] == project_with_sources["grooming_id"]
    assert project_with_sources["queued_id"] not in {h["source_id"] for h in hits}
    for hit in hits:
        assert hit["title"] == "Pricing page"
        assert hit["snippet"]  # non-empty snippet from the matched text
        assert hit["score"] > 0  # ts_rank_cd is unbounded; order is the contract
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    # no cross-topic leakage: the vet source does not match "grooming"
    assert project_with_sources["vet_id"] not in {h["source_id"] for h in hits}


async def test_vector_search_ranks_by_embedding(
    api, owner: TestUser, project_with_sources
) -> None:
    project_id = project_with_sources["project_id"]
    embedder = project_with_sources["embedder"]
    # search embeds the query with the SAME fake the chunks were embedded
    # with (mirrors production: one configured model for pipeline + query)
    api.app.state.research_embedder = embedder

    response = await api.get(
        f"/projects/{project_id}/search/vector",
        params={"q": "grooming prices"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200, response.text
    hits = response.json()
    assert len(hits) >= 1
    assert hits[0]["source_id"] == project_with_sources["grooming_id"]
    assert hits[0]["score"] > 0.9  # keyword-aligned chunks are near-identical
    # top-k vector search returns nearest chunks, not only exact matches:
    # anything from the vet source ranks below the grooming hits
    vet_hits = [h for h in hits if h["source_id"] == project_with_sources["vet_id"]]
    if vet_hits:
        assert all(h["score"] < hits[0]["score"] for h in vet_hits)
    # scores descend
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    # the query was embedded once, as the raw query text
    assert embedder.calls[-1] == ["grooming prices"]


async def test_empty_and_no_results_are_sane(
    api, owner: TestUser, project_with_sources
) -> None:
    project_id = project_with_sources["project_id"]
    for endpoint in ("text", "vector"):
        empty = await api.get(
            f"/projects/{project_id}/search/{endpoint}",
            params={"q": ""},
            headers=auth_headers(owner),
        )
        assert empty.status_code == 200, empty.text
        assert empty.json() == []

    # text search: a term nobody used matches nothing
    missing = await api.get(
        f"/projects/{project_id}/search/text",
        params={"q": "zzznotpresentterm"},
        headers=auth_headers(owner),
    )
    assert missing.status_code == 200, missing.text
    assert missing.json() == []

    # vector search: an unaligned query still returns nearest chunks (top-k
    # has no empty set), but ranked clearly below an aligned query
    embedder = project_with_sources["embedder"]
    api.app.state.research_embedder = embedder
    aligned = (await api.get(
        f"/projects/{project_id}/search/vector",
        params={"q": "grooming"},
        headers=auth_headers(owner),
    )).json()
    unaligned = (await api.get(
        f"/projects/{project_id}/search/vector",
        params={"q": "zzznotpresentterm"},
        headers=auth_headers(owner),
    )).json()
    assert unaligned[0]["score"] < aligned[0]["score"]


async def test_search_requires_authentication(api, project_with_sources) -> None:
    project_id = project_with_sources["project_id"]
    assert (await api.get(
        f"/projects/{project_id}/search/text", params={"q": "grooming"}
    )).status_code == 401
    assert (await api.get(
        f"/projects/{project_id}/search/vector", params={"q": "grooming"}
    )).status_code == 401


async def test_viewer_can_search_but_still_cannot_mutate(
    api, owner: TestUser, org: str, user_factory, project_with_sources
) -> None:
    viewer = await user_factory("search-viewer")
    await _invite_project_viewer(
        api, owner, org, viewer, project_with_sources["project_id"]
    )
    for endpoint in ("text", "vector"):
        assert (await api.get(
            f"/projects/{project_with_sources['project_id']}/search/{endpoint}",
            params={"q": "grooming"},
            headers=auth_headers(viewer),
        )).status_code == 200
    # read-level role: source creation still forbidden
    assert (await api.post(
        f"/projects/{project_with_sources['project_id']}/sources",
        json={
            "notebook_id": project_with_sources["notebook_id"],
            "title": "t",
            "content": "c",
        },
        headers=auth_headers(viewer),
    )).status_code == 403


async def test_vector_search_unconfigured_returns_503(
    api, owner: TestUser, project_with_sources
) -> None:
    """No embedding configured: text search still works, vector search is
    a typed 503 — never a bare 500."""
    from modules.research.infrastructure.embedder import EsperantoEmbedder

    api.app.state.research_embedder = EsperantoEmbedder(
        provider="", model_name=""
    )
    project_id = project_with_sources["project_id"]
    text = await api.get(
        f"/projects/{project_id}/search/text",
        params={"q": "grooming"},
        headers=auth_headers(owner),
    )
    assert text.status_code == 200, text.text
    vector = await api.get(
        f"/projects/{project_id}/search/vector",
        params={"q": "grooming"},
        headers=auth_headers(owner),
    )
    assert vector.status_code == 503
    assert "not configured" in vector.json()["detail"]


async def test_vector_search_embedder_absent_returns_503(
    api, owner: TestUser, project_with_sources
) -> None:
    """research_embedder never installed on app.state (dependency resolves
    to None): still a typed 503, never a bare 500 escaping the wrapper."""
    del api.app.state.research_embedder
    vector = await api.get(
        f"/projects/{project_with_sources['project_id']}/search/vector",
        params={"q": "grooming"},
        headers=auth_headers(owner),
    )
    assert vector.status_code == 503
    assert "not configured" in vector.json()["detail"]


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
    assert (await api.post(
        "/invitations/accept", json={"token": token},
        headers=auth_headers(invitee),
    )).status_code == 204
