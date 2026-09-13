"""HTTP seam: embeddings + source_chunks storage (ticket #24, spec #21).

Bullet 3/4: processed Sources become embeddable. Chunks are embedded
through the Embedder port (Esperanto in the composition root, a
deterministic fake here — no real provider APIs), validated against the
vector(1536) contract, and stored on research.source_chunks. Embedding
failures are typed, land the source in a visible failed state, and are
retryable; the unconfigured case fails cleanly the same way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import DeterministicEmbedder, FlakyEmbedder
from tests.product.research_helpers import (
    LONG_TEXT,
    create_text_source,
    new_notebook,
    new_project,
)


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("embedding-owner")


@pytest_asyncio.fixture
async def drain_with(settings) -> AsyncIterator:
    """The dispatcher with an explicitly chosen embedder — the composition
    seam the acceptance criteria mandate."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.dispatcher import drain_pending_sources

    engine = create_engine(settings.database_dsn)

    async def _drain(embedder) -> int:
        return await drain_pending_sources(engine, embedder=embedder)

    yield _drain
    await engine.dispose()


async def _chunk_embeddings(settings, source_id: str) -> list[dict]:
    """Chunk rows with embedding presence/dimensions — asyncpg returns the
    vector type as text, so assert through SQL instead of parsing."""
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        rows = await conn.fetch(
            "select chunk_index, content, embedding is not null as has_embedding,"
            "       vector_dims(embedding) as dimensions"
            " from research.source_chunks where source_id = $1::uuid"
            " order by chunk_index",
            source_id,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def test_processed_source_chunks_carry_embeddings(
    api, owner: TestUser, org: str, settings, drain_with
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    source_id = source["id"]
    embedder = DeterministicEmbedder()

    assert (await drain_with(embedder)) >= 1

    status = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert status["status"] == "completed"

    chunks = await _chunk_embeddings(settings, source_id)
    assert len(chunks) >= 2
    assert all(c["has_embedding"] for c in chunks)
    assert all(c["dimensions"] == 1536 for c in chunks)
    # the pipeline embedded the actual chunk contents, in one batch
    assert embedder.calls == [[c["content"] for c in chunks]]


async def test_embedding_failure_leaves_source_retryable(
    api, owner: TestUser, org: str, settings, drain_with
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    source_id = source["id"]
    delegate = DeterministicEmbedder()
    flaky = FlakyEmbedder(delegate)

    assert (await drain_with(flaky)) >= 1
    failed = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert failed["status"] == "failed"
    assert "simulated provider outage" in failed["error"]

    retried = await api.post(
        f"/projects/{project_id}/sources/{source_id}/retry",
        headers=auth_headers(owner),
    )
    assert retried.status_code == 202

    assert (await drain_with(flaky)) >= 1
    recovered = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert recovered["status"] == "completed"
    chunks = await _chunk_embeddings(settings, source_id)
    assert len(chunks) >= 2
    assert all(c["has_embedding"] for c in chunks)


async def test_unconfigured_embedding_model_fails_visibly_and_recovers(
    api, owner: TestUser, org: str, settings, drain_with
) -> None:
    """The real composition-root path with no provider configured: typed
    failure per source (never a bare exception, never a startup crash),
    and a configured retry recovers."""
    from modules.research.infrastructure.embedder import EsperantoEmbedder

    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    source_id = source["id"]

    unconfigured = EsperantoEmbedder(provider="", model_name="")
    assert (await drain_with(unconfigured)) >= 1
    failed = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert failed["status"] == "failed"
    assert "not configured" in failed["error"]

    assert (await api.post(
        f"/projects/{project_id}/sources/{source_id}/retry",
        headers=auth_headers(owner),
    )).status_code == 202
    assert (await drain_with(DeterministicEmbedder())) >= 1
    recovered = (await api.get(
        f"/projects/{project_id}/sources/{source_id}",
        headers=auth_headers(owner),
    )).json()
    assert recovered["status"] == "completed"


async def test_repeated_processing_replaces_embeddings_without_duplicates(
    api, owner: TestUser, org: str, settings, drain_with
) -> None:
    """Retry idempotency at the storage layer: chunk rows (with vectors)
    are replaced, never duplicated."""
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    source = await create_text_source(api, owner, project_id, notebook_id, LONG_TEXT)
    source_id = source["id"]
    embedder = DeterministicEmbedder()

    assert (await drain_with(embedder)) >= 1
    first_pass = await _chunk_embeddings(settings, source_id)
    assert len(first_pass) >= 2

    # duplicate the submission event, reprocess: same rows come back
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "insert into public.outbox_events (event_type, payload)"
            " values ('SourceSubmitted', $1::jsonb)",
            '{"source_id": "%s", "organization_id": "%s", "project_id": "%s",'
            ' "notebook_id": "%s"}'
            % (source_id, org, project_id, notebook_id),
        )
    finally:
        await conn.close()
    assert (await drain_with(embedder)) == 1
    assert (await _chunk_embeddings(settings, source_id)) == first_pass


# --- pure unit tests: the embedder's typed-error contract (no managed DB) --


async def test_esperanto_embedder_unconfigured_raises_typed_error() -> None:
    from modules.research.application.errors import EmbeddingConfigurationError
    from modules.research.infrastructure.embedder import EsperantoEmbedder

    with pytest.raises(EmbeddingConfigurationError, match="not configured"):
        await EsperantoEmbedder(provider="", model_name="m").embed(["x"])
    with pytest.raises(EmbeddingConfigurationError, match="not configured"):
        await EsperantoEmbedder(provider="openai", model_name="").embed(["x"])


async def test_esperanto_embedder_wraps_provider_failures(monkeypatch) -> None:
    from modules.research.application.errors import EmbeddingProviderError
    from modules.research.infrastructure.embedder import EsperantoEmbedder

    class _BrokenModel:
        async def aembed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("network down")

    embedder = EsperantoEmbedder(provider="openai", model_name="m", api_key="k")
    monkeypatch.setattr(embedder, "_build_model", lambda: _BrokenModel())
    with pytest.raises(EmbeddingProviderError, match="network down"):
        await embedder.embed(["x"])


async def test_embed_chunks_validates_provider_contract() -> None:
    from modules.research.application.errors import EmbeddingProviderError
    from modules.research.application.processing import embed_chunks

    class _WrongCount:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0]]

    class _WrongDims:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 2.0] for _ in texts]

    with pytest.raises(EmbeddingProviderError, match="1 vectors for 2 chunks"):
        await embed_chunks(_WrongCount(), ["a", "b"])
    with pytest.raises(EmbeddingProviderError, match="dimension 2"):
        await embed_chunks(_WrongDims(), ["a", "b"])
