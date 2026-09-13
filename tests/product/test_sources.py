"""HTTP seam: text Source ingestion + async processing (ticket #23, spec #21).

Bullet 2/4 of the research tracer bullet. An Application user pastes text
into a Notebook and the system ingests it as a Source, processed
asynchronously off-request (ADR-004): the create endpoint returns a queued
source immediately, an in-process dispatcher over the existing
outbox_events table runs extraction→chunking, and the user polls status
and retries failures. Tests drive the dispatcher explicitly for
determinism (no sleeps), which the production loop in serve.py wraps.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.research_helpers import (
    LONG_TEXT,
    create_text_source,
    new_notebook,
    new_project,
)


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("source-owner")


@pytest_asyncio.fixture
async def drain(settings) -> AsyncIterator:
    """Run the in-process dispatcher on demand — deterministic processing
    without relying on the serve.py background loop. The embedder is the
    deterministic fake (ticket #24 seam): no real provider APIs."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.dispatcher import drain_pending_sources
    from tests.product.fakes import DeterministicEmbedder

    engine = create_engine(settings.database_dsn)
    embedder = DeterministicEmbedder()

    async def _drain() -> int:
        return await drain_pending_sources(engine, embedder=embedder)

    yield _drain
    await engine.dispose()


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


async def _outbox_payloads(settings, event_type: str, source_id: str) -> list[dict]:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        rows = await conn.fetch(
            "select payload from public.outbox_events"
            " where event_type = $1 and payload->>'source_id' = $2"
            " order by occurred_at",
            event_type,
            source_id,
        )
        return [json.loads(row["payload"]) for row in rows]
    finally:
        await conn.close()


async def _chunk_rows(settings, source_id: str) -> list[dict]:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        rows = await conn.fetch(
            "select organization_id, project_id, notebook_id, chunk_index, content"
            " from research.source_chunks where source_id = $1::uuid"
            " order by chunk_index",
            source_id,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def test_paste_text_source_queues_then_dispatcher_completes(
    api, owner: TestUser, org: str, settings, drain
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)

    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    assert source["status"] == "queued"  # immediate, 202 — never blocks
    assert source["type"] == "text"
    assert source["organization_id"] == org
    assert source["project_id"] == project_id
    assert source["notebook_id"] == notebook_id
    assert source["error"] is None
    source_id = source["id"]

    # the submit event went out in the same transaction as the source row
    submitted = await _outbox_payloads(settings, "SourceSubmitted", source_id)
    assert len(submitted) == 1
    assert submitted[0]["organization_id"] == org
    assert submitted[0]["project_id"] == project_id

    assert (await drain()) >= 1

    polled = await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )
    assert polled.status_code == 200
    assert polled.json()["status"] == "completed"
    assert polled.json()["error"] is None

    chunks = await _chunk_rows(settings, source_id)
    assert len(chunks) >= 2  # token-based chunking actually split the text
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert str(chunk["organization_id"]) == org
        assert str(chunk["project_id"]) == project_id
        assert str(chunk["notebook_id"]) == notebook_id
        assert chunk["content"].strip()

    completed = await _outbox_payloads(settings, "SourceProcessingCompleted", source_id)
    assert len(completed) == 1
    assert completed[0]["status"] == "completed"

    listed = (await api.get(
        f"/projects/{project_id}/sources", headers=auth_headers(owner)
    )).json()
    assert [s["id"] for s in listed] == [source_id]


async def test_short_text_yields_a_single_chunk(
    api, owner: TestUser, org: str, settings, drain
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, "tiny note")

    assert (await drain()) >= 1

    chunks = await _chunk_rows(settings, source["id"])
    assert len(chunks) == 1
    assert chunks[0]["content"] == "tiny note"


async def test_retry_after_induced_failure_recovers_and_is_idempotent(
    api, owner: TestUser, org: str, settings, drain, monkeypatch
) -> None:
    from modules.research.application import processing

    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    source_id = source["id"]

    def _boom(_text: str) -> list[str]:
        raise RuntimeError("chunker exploded")

    monkeypatch.setattr(processing, "chunk_text", _boom)
    assert (await drain()) >= 1

    failed = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert failed["status"] == "failed"
    assert "chunker exploded" in failed["error"]
    completed = await _outbox_payloads(settings, "SourceProcessingCompleted", source_id)
    assert completed[-1]["status"] == "failed"

    monkeypatch.undo()  # the transient fault clears

    retried = await api.post(
        f"/projects/{project_id}/sources/{source_id}/retry",
        headers=auth_headers(owner),
    )
    assert retried.status_code == 202
    assert retried.json()["status"] == "queued"
    assert retried.json()["error"] is None

    assert (await drain()) >= 1
    recovered = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert recovered["status"] == "completed"
    first_pass = await _chunk_rows(settings, source_id)
    assert len(first_pass) >= 2

    # repeated execution is idempotent: delete-and-reinsert, no duplicates.
    # (The API refuses re-retry from completed — 409 — so duplicate *events*,
    # not duplicate retries, are the realistic repeated-execution hazard:
    # two deliveries of the same submission must yield the same rows.)
    assert (await drain()) == 0  # the retry re-queued exactly one event
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "insert into public.outbox_events (event_type, payload)"
            " values ('SourceSubmitted', $1::jsonb)",
            json.dumps(
                {
                    "source_id": source_id,
                    "organization_id": org,
                    "project_id": project_id,
                    "notebook_id": notebook_id,
                }
            ),
        )
    finally:
        await conn.close()
    assert (await drain()) == 1  # the duplicate delivery is consumed
    second_pass = await _chunk_rows(settings, source_id)
    assert second_pass == first_pass


async def test_unauthenticated_requests_are_rejected(
    api, owner: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)

    assert (await api.post(
        f"/projects/{project_id}/sources",
        json={"notebook_id": notebook_id, "title": "t", "content": "c"},
    )).status_code == 401

    source_id = uuid.uuid4()
    assert (await api.get(
        f"/projects/{project_id}/sources/{source_id}"
    )).status_code == 401
    assert (await api.post(
        f"/projects/{project_id}/sources/{source_id}/retry"
    )).status_code == 401


async def test_viewer_reads_status_but_cannot_create_or_retry(
    api, owner: TestUser, org: str, user_factory, drain
) -> None:
    viewer = await user_factory("source-viewer")
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    await _invite_project_viewer(api, owner, org, viewer, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    assert (await drain()) >= 1

    assert (await api.get(
        f"/projects/{project_id}/sources/{source['id']}",
        headers=auth_headers(viewer),
    )).status_code == 200
    assert (await api.get(
        f"/projects/{project_id}/sources", headers=auth_headers(viewer)
    )).status_code == 200

    assert (await api.post(
        f"/projects/{project_id}/sources",
        json={"notebook_id": notebook_id, "title": "t", "content": "c"},
        headers=auth_headers(viewer),
    )).status_code == 403
    assert (await api.post(
        f"/projects/{project_id}/sources/{source['id']}/retry",
        headers=auth_headers(viewer),
    )).status_code == 403


async def test_cross_tenant_status_and_retry_are_denied(
    api, owner: TestUser, org: str, user_factory, settings
) -> None:
    other = await user_factory("other-owner")
    other_org = (await api.post(
        "/organizations",
        json={"name": f"Org {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(other),
    )).json()["id"]

    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)

    # a member of another Organization cannot read, list, or retry the job:
    # the tenant-safe answer to guessed IDs is 404
    assert (await api.get(
        f"/projects/{project_id}/sources/{source['id']}",
        headers=auth_headers(other),
    )).status_code == 404
    assert (await api.get(
        f"/projects/{project_id}/sources", headers=auth_headers(other)
    )).status_code == 404
    assert (await api.post(
        f"/projects/{project_id}/sources/{source['id']}/retry",
        headers=auth_headers(other),
    )).status_code == 404

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "delete from public.organizations where id = $1::uuid", other_org
        )
    finally:
        await conn.close()


async def test_chunker_port_semantics() -> None:
    """The text-path port of open_notebook/utils/chunking.py: 400-token
    target, 15% overlap, recursive character splitting, min-chunk filter.
    Assertions use the ported token_count so they hold under both the
    tiktoken and the offline word-count fallback."""
    from modules.research.application.processing import (
        CHUNK_OVERLAP,
        CHUNK_SIZE,
        chunk_text,
        token_count,
    )

    assert CHUNK_SIZE == 400
    assert CHUNK_OVERLAP == 60  # 15% of 400
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("hello world") == ["hello world"]

    chunks = chunk_text(LONG_TEXT)
    assert len(chunks) >= 2
    assert chunks[0].startswith("The competitor offers full grooming")
    assert all(token_count(c) <= CHUNK_SIZE for c in chunks)
    # in-order coverage: each chunk's start appears later in the text than
    # the previous chunk's start (nothing reordered, nothing invented)
    positions = [LONG_TEXT.find(c[:20]) for c in chunks]
    assert positions == sorted(positions)
    assert all(p >= 0 for p in positions)
