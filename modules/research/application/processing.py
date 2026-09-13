"""The text processing pipeline (ticket #23) — port of upstream's
source_graph text path: token-based chunking (open_notebook/utils/chunking.py
semantics) applied to the Source's full_text, run off-request by the
dispatcher (ADR-004).

Port semantics, deliberately narrowed to the text path:
- 400-token target, 15% overlap (60 tokens), recursive character splitting
  in upstream's separator order, short text returned as a single chunk,
  fragments below 5 tokens dropped when they are not the only chunk.
- Chunk sizing is token-based via ``token_count`` (tiktoken o200k_base,
  falling back to a word-count estimate offline) — the same function the
  assertions in tests use, so behavior holds with or without tiktoken.

Defaults are module constants, not environment reads (plan §14.2: the
application layer reads no environment; upstream's env overrides were not
ported).
"""

from uuid import UUID, uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter

from modules.platform.application.errors import NotFoundError
from modules.platform.domain.entities import OutboxEvent
from modules.research.application.errors import EmbeddingProviderError
from modules.research.domain.embedder import EMBEDDING_DIMENSIONS, Embedder
from modules.research.domain.entities import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
    SourceChunk,
)
from modules.research.domain.events import SOURCE_PROCESSING_COMPLETED
from modules.research.domain.unit_of_work import ResearchUnit

CHUNK_SIZE = 400
CHUNK_OVERLAP = int(CHUNK_SIZE * 0.15)  # upstream default: 15% of chunk size
MIN_CHUNK_SIZE = 5
_SEPARATORS = ["\n\n", "\n", ". ", ", ", " ", ""]


def token_count(text: str) -> int:
    """Token count via tiktoken's o200k_base (upstream default), with the
    upstream fallback when tiktoken is unavailable offline."""
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(text, disallowed_special=()))
    except (ImportError, OSError):
        return int(len(text.split()) * 1.3)


def chunk_text(text: str) -> list[str]:
    """Split text into token-sized chunks (upstream plain-text semantics)."""
    if not text or not text.strip():
        return []

    if token_count(text) <= CHUNK_SIZE:
        return [text]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=token_count,
        separators=_SEPARATORS,
    )
    chunks = [c.strip() for c in splitter.split_text(text) if c and c.strip()]

    # Drop punctuation/single-character fragments, but never empty the list.
    if MIN_CHUNK_SIZE > 0 and len(chunks) > 1:
        kept = [c for c in chunks if token_count(c) >= MIN_CHUNK_SIZE]
        if kept:
            chunks = kept

    return chunks


class SourceProcessingError(Exception):
    """A permanent pipeline failure (mirrors upstream's ValueError path);
    recorded on the source row and surfaced through the status endpoint."""


async def embed_chunks(
    embedder: Embedder, contents: list[str]
) -> list[list[float]]:
    """Embed chunk contents, validating the provider contract before any
    row write: one vector per chunk, each vector(1536) (plan §9)."""
    vectors = await embedder.embed(contents)
    if len(vectors) != len(contents):
        raise EmbeddingProviderError(
            f"embedding provider returned {len(vectors)} vectors"
            f" for {len(contents)} chunks"
        )
    normalized: list[list[float]] = []
    for vector in vectors:
        values = [float(v) for v in vector]
        if len(values) != EMBEDDING_DIMENSIONS:
            raise EmbeddingProviderError(
                f"embedding provider returned dimension {len(values)},"
                f" expected {EMBEDDING_DIMENSIONS}"
            )
        normalized.append(values)
    return normalized


async def process_text_source(
    unit: ResearchUnit,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID,
    embedder: Embedder,
) -> None:
    """Run the text pipeline for one source inside the caller's unit.

    Everything — status flip, chunk + embedding replace, completion
    event — commits in the dispatcher's single transaction. Idempotent
    under repeated execution: chunks are delete-and-reinsert, so
    reprocessing yields the same rows. Embedding failures are typed and
    leave the source failed/retryable (never bare exceptions).
    """
    source = await unit.sources.get(organization_id, project_id, source_id)
    if source is None:
        raise NotFoundError("source not found")

    await unit.sources.update_status(
        organization_id, project_id, source_id, status=STATUS_RUNNING, error=None
    )

    if not source.full_text or not source.full_text.strip():
        raise SourceProcessingError("source has no text to process")

    contents = chunk_text(source.full_text)
    vectors = await embed_chunks(embedder, contents)
    chunks = [
        SourceChunk(
            id=uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            notebook_id=source.notebook_id,
            source_id=source_id,
            chunk_index=index,
            content=content,
            embedding=vector,
        )
        for index, (content, vector) in enumerate(zip(contents, vectors))
    ]
    await unit.source_chunks.replace_for_source(
        organization_id, project_id, source_id, source.notebook_id, chunks
    )
    await unit.sources.update_status(
        organization_id, project_id, source_id, status=STATUS_COMPLETED, error=None
    )
    await unit.outbox.add(
        OutboxEvent(
            event_type=SOURCE_PROCESSING_COMPLETED,
            payload={
                "source_id": str(source_id),
                "organization_id": str(organization_id),
                "project_id": str(project_id),
                "status": STATUS_COMPLETED,
                "chunk_count": len(chunks),
            },
        )
    )


async def fail_text_source(
    unit: ResearchUnit,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID,
    error: str,
) -> None:
    """Record a pipeline failure in its own transaction: the source flips
    to failed with the error message and a completion event still goes
    out, so the failure is observable (and retryable) rather than silent.
    """
    source = await unit.sources.get(organization_id, project_id, source_id)
    if source is None:
        raise NotFoundError("source not found")
    error = error[:500]
    await unit.sources.update_status(
        organization_id,
        project_id,
        source_id,
        status=STATUS_FAILED,
        error=error,
    )
    await unit.outbox.add(
        OutboxEvent(
            event_type=SOURCE_PROCESSING_COMPLETED,
            payload={
                "source_id": str(source_id),
                "organization_id": str(organization_id),
                "project_id": str(project_id),
                "status": STATUS_FAILED,
                "error": error,
            },
        )
    )


__all__ = [
    "CHUNK_OVERLAP",
    "CHUNK_SIZE",
    "MIN_CHUNK_SIZE",
    "SourceProcessingError",
    "chunk_text",
    "embed_chunks",
    "fail_text_source",
    "process_text_source",
    "token_count",
]
