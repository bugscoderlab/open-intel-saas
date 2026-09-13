"""HTTP seam: file Source ingestion (ticket #29, spec #26, Phase 2 backfill 2/3).

The vertical slice over the storage service (#28): multipart upload →
hardened validation → stored object + registry row + Source (type=file)
in one request transaction → async pipeline (ADR-004) downloads the
object, extracts text with content-core, then the unchanged
chunk→embed→complete path. Download = short-lived signed URL from the
storage port, only after source.read passes.

Storage is the recording fake from tests/product/fakes.py (the
composition seam) — no real bucket is touched.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import DeterministicEmbedder
from tests.product.research_helpers import new_notebook, new_project


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("file-source-owner")


@pytest_asyncio.fixture
async def other(user_factory) -> TestUser:
    return await user_factory("file-source-other")


@pytest_asyncio.fixture
async def drain(settings, api) -> AsyncIterator:
    """In-process dispatcher with the app's recording storage — the file
    pipeline reads objects back through the port (ticket #28 seam)."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.dispatcher import drain_pending_sources

    engine = create_engine(settings.database_dsn)
    storage = api.app.state.research_storage

    async def _drain(embedder=None) -> int:
        return await drain_pending_sources(
            engine,
            embedder=embedder or DeterministicEmbedder(),
            storage=storage,
        )

    yield _drain
    await engine.dispose()


async def _upload(
    api,
    user: TestUser,
    project_id: str,
    filename: str,
    data: bytes,
    content_type: str,
    **fields,
):
    return await api.post(
        f"/projects/{project_id}/sources/file",
        files={"file": (filename, data, content_type)},
        data={k: str(v) for k, v in fields.items() if v is not None},
        headers=auth_headers(user),
    )


async def _registry_row(settings, source_id: str):
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        row = await conn.fetchrow(
            "select object_key, checksum, size_bytes, content_type"
            " from research.source_files where source_id = $1::uuid",
            source_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def _source(api, user: TestUser, project_id: str, source_id: str) -> dict:
    response = await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_upload_txt_file_queues_then_pipeline_extracts_chunks_and_embeds(
    api, owner: TestUser, org: str, settings, drain
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    body = b"Full grooming: RM88, September.\nEar cleaning: RM15.\n"
    embedder = DeterministicEmbedder()

    response = await _upload(
        api,
        owner,
        project_id,
        "prices.txt",
        body,
        "text/plain",
        notebook_id=notebook_id,
        title="Price list",
    )
    assert response.status_code == 202, response.text
    source = response.json()
    assert source["type"] == "file"
    assert source["status"] == "queued"
    assert source["notebook_id"] == notebook_id
    assert source["error"] is None
    source_id = source["id"]

    # registry row landed in the same request transaction
    row = await _registry_row(settings, source_id)
    assert row is not None
    assert row["size_bytes"] == len(body)
    assert row["content_type"] == "text/plain"
    assert row["object_key"].startswith(f"{org}/{project_id}/{source_id}/")

    assert (await drain(embedder)) >= 1
    completed = await _source(api, owner, project_id, source_id)
    assert completed["status"] == "completed"
    assert completed["error"] is None

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        full_text = await conn.fetchval(
            "select full_text from research.sources where id = $1::uuid", source_id
        )
        chunks = await conn.fetch(
            "select content from research.source_chunks where source_id = $1::uuid"
            " order by chunk_index",
            source_id,
        )
    finally:
        await conn.close()
    assert "Full grooming: RM88" in full_text
    assert len(chunks) == 1
    # the pipeline embedded the extracted text (via the fake seam)
    assert embedder.calls == [[full_text]]


async def test_upload_without_notebook_is_allowed(
    api, owner: TestUser, org: str, drain
) -> None:
    project_id = await new_project(api, owner, org)
    response = await _upload(
        api, owner, project_id, "loose.md", b"# stray notes", "text/markdown"
    )
    assert response.status_code == 202, response.text
    source = response.json()
    assert source["notebook_id"] is None

    assert (await drain()) >= 1
    completed = await _source(api, owner, project_id, source["id"])
    assert completed["status"] == "completed"


async def test_corrupt_pdf_fails_typed_and_is_retryable(
    api, owner: TestUser, org: str, settings, drain
) -> None:
    project_id = await new_project(api, owner, org)
    # passes the %PDF magic-byte gate, but content-core cannot parse it
    body = b"%PDF-1.4 this is not a real pdf document"
    response = await _upload(
        api, owner, project_id, "broken.pdf", body, "application/pdf"
    )
    assert response.status_code == 202, response.text
    source_id = response.json()["id"]

    assert (await drain()) >= 1
    failed = await _source(api, owner, project_id, source_id)
    assert failed["status"] == "failed"
    assert failed["error"]

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        left = await conn.fetchval(
            "select count(*) from research.source_chunks where source_id = $1::uuid",
            source_id,
        )
    finally:
        await conn.close()
    assert left == 0  # no partial chunks on failure

    retried = await api.post(
        f"/projects/{project_id}/sources/{source_id}/retry",
        headers=auth_headers(owner),
    )
    assert retried.status_code == 202
    assert (await drain()) >= 1
    still_failed = await _source(api, owner, project_id, source_id)
    assert still_failed["status"] == "failed"


async def test_spoofed_upload_rejected_before_any_write(
    api, owner: TestUser, org: str, settings, drain
) -> None:
    project_id = await new_project(api, owner, org)
    response = await _upload(
        api,
        owner,
        project_id,
        "disguised.pdf",
        b"plain text, not a pdf",
        "application/pdf",
    )
    assert response.status_code == 422, response.text
    # nothing queued: the dispatcher has nothing to consume for this
    assert (await drain()) == 0


async def test_download_url_requires_source_read_and_never_persists(
    api, owner: TestUser, other: TestUser, org: str, drain
) -> None:
    project_id = await new_project(api, owner, org)
    response = await _upload(
        api, owner, project_id, "prices.txt", b"grooming RM88", "text/plain"
    )
    source_id = response.json()["id"]
    assert (await drain()) >= 1

    ok = await api.get(
        f"/projects/{project_id}/sources/{source_id}/file",
        headers=auth_headers(owner),
    )
    assert ok.status_code == 200, ok.text
    url = ok.json()["url"]
    assert url.startswith("signed://")

    storage = api.app.state.research_storage
    assert storage.sign_calls, "signed URL must come from the storage port"

    # other-org user: the tenant-safe 404, never a URL
    denied = await api.get(
        f"/projects/{project_id}/sources/{source_id}/file",
        headers=auth_headers(other),
    )
    assert denied.status_code == 404


async def test_cross_tenant_upload_and_get_are_isolated(
    api, owner: TestUser, other: TestUser, org: str
) -> None:
    project_id = await new_project(api, owner, org)
    response = await _upload(
        api, owner, project_id, "private.txt", b"secret", "text/plain"
    )
    source_id = response.json()["id"]

    guessed_get = await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(other),
    )
    assert guessed_get.status_code == 404
    guessed_file = await api.get(
        f"/projects/{project_id}/sources/{source_id}/file",
        headers=auth_headers(other),
    )
    assert guessed_file.status_code == 404

    # the other user's own org works independently
    other_org = (
        await api.post(
            "/organizations",
            json={"name": f"Org {uuid.uuid4().hex[:8]}"},
            headers=auth_headers(other),
        )
    ).json()["id"]
    other_project = await new_project(api, other, other_org)
    ok = await _upload(
        api, other, other_project, "own.txt", b"mine", "text/plain"
    )
    assert ok.status_code == 202, ok.text
