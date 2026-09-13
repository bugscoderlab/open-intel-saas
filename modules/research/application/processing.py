"""The processing pipeline (tickets #23/#29) — port of upstream's
source_graph text path plus the file path: token-based chunking
(open_notebook/utils/chunking.py semantics) applied to the Source's
full_text, run off-request by the dispatcher (ADR-004).

Port semantics, deliberately narrowed to the text path:
- 400-token target, 15% overlap (60 tokens), recursive character splitting
  in upstream's separator order, short text returned as a single chunk,
  fragments below 5 tokens dropped when they are not the only chunk.
- Chunk sizing is token-based via ``token_count`` (tiktoken o200k_base,
  falling back to a word-count estimate offline) — the same function the
  assertions in tests use, so behavior holds with or without tiktoken.

The file path (ticket #29) adds one step ahead of chunking: the stored
object's bytes are read through the FileStorage port and converted to
text with content-core (upstream's extractor). content-core signals soft
failures by returning a sentinel title/content pair rather than raising —
the same detection upstream uses — which we turn into a typed
SourceProcessingError so the source lands failed and retryable, never
"completed" with an error body.

Defaults are module constants, not environment reads (plan §14.2: the
application layer reads no environment; upstream's env overrides were not
ported).
"""

import os
import tempfile
from uuid import UUID, uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter

from modules.platform.application.errors import NotFoundError, ServiceUnavailableError
from modules.platform.domain.entities import OutboxEvent
from modules.platform.domain.storage import FileStorage
from modules.research.application.errors import EmbeddingProviderError
from modules.research.domain.embedder import EMBEDDING_DIMENSIONS, Embedder
from modules.research.domain.entities import (
    SOURCE_TYPE_FILE,
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


# content-core's soft-failure sentinel (same detection as upstream's
# source_graph): it returns this pair instead of raising.
_EXTRACTION_FAILED_PREFIX = "Failed to extract content:"


async def extract_file_text(data: bytes, filename: str) -> str:
    """Convert stored object bytes to text via content-core (ticket #29).

    Raises SourceProcessingError for anything content-core cannot turn
    into non-empty text — the failure is typed and retryable, never a
    "completed" source whose body is the error string (upstream rule).
    """
    from content_core import extract_content

    # content-core extracts by file path (upstream hands it the stored
    # file the same way); the pipeline's input is the object's bytes.
    suffix = os.path.splitext(filename)[1] or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        processed = await extract_content(file_path=tmp_path)
    finally:
        os.unlink(tmp_path)

    if processed.title == "Error" and (processed.content or "").startswith(
        _EXTRACTION_FAILED_PREFIX
    ):
        raise SourceProcessingError(
            "could not extract text from the stored file"
            " (unrecognized, corrupt, or unsupported content)"
        )
    text = (processed.content or "").strip()
    if not text:
        raise SourceProcessingError(
            "the stored file yielded no extractable text"
        )
    return text


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


async def _chunk_embed_complete(
    unit: ResearchUnit,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID,
    full_text: str,
    notebook_id: UUID | None,
    embedder: Embedder,
) -> None:
    """The shared pipeline tail: chunk → embed → replace → completed →
    completion event, all in the caller's transaction (idempotent under
    repeated execution — chunks are delete-and-reinsert)."""
    contents = chunk_text(full_text)
    vectors = await embed_chunks(embedder, contents)
    chunks = [
        SourceChunk(
            id=uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            notebook_id=notebook_id,
            source_id=source_id,
            chunk_index=index,
            content=content,
            embedding=vector,
        )
        for index, (content, vector) in enumerate(zip(contents, vectors))
    ]
    await unit.source_chunks.replace_for_source(
        organization_id, project_id, source_id, notebook_id, chunks
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


async def process_source(
    unit: ResearchUnit,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID,
    embedder: Embedder,
    storage: FileStorage | None,
) -> None:
    """Pipeline entry: dispatch by source type (ticket #29). The status
    flip to running is the same for every type; what differs is how
    full_text is obtained."""
    source = await unit.sources.get(organization_id, project_id, source_id)
    if source is None:
        raise NotFoundError("source not found")

    await unit.sources.update_status(
        organization_id, project_id, source_id, status=STATUS_RUNNING, error=None
    )

    if source.type == SOURCE_TYPE_FILE:
        extracted = await _extract_source_file_text(
            unit, storage, organization_id=organization_id, project_id=project_id,
            source_id=source_id,
        )
        await unit.sources.update_full_text(
            organization_id, project_id, source_id, full_text=extracted
        )
        full_text: str | None = extracted
    else:
        full_text = source.full_text

    if not full_text or not full_text.strip():
        raise SourceProcessingError("source has no text to process")

    await _chunk_embed_complete(
        unit,
        organization_id=organization_id,
        project_id=project_id,
        source_id=source_id,
        full_text=full_text,
        notebook_id=source.notebook_id,
        embedder=embedder,
    )


async def _extract_source_file_text(
    unit: ResearchUnit,
    storage: FileStorage | None,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID,
) -> str:
    """File path: registry row → object bytes through the port → text."""
    if storage is None:
        raise ServiceUnavailableError("file storage is not configured")
    registry = await unit.source_files.get_for_source(
        organization_id, project_id, source_id
    )
    if registry is None:
        raise SourceProcessingError("source has no stored file")
    data = await storage.get(registry.object_key)
    filename = registry.object_key.rsplit("/", 1)[-1]
    return await extract_file_text(data, filename)


async def process_text_source(
    unit: ResearchUnit,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID,
    embedder: Embedder,
) -> None:
    """Run the text pipeline for one source inside the caller's unit.

    Kept as the explicit text-path entry (and used by existing callers);
    equivalent to ``process_source`` for text sources. Everything —
    status flip, chunk + embedding replace, completion event — commits
    in the dispatcher's single transaction. Idempotent under repeated
    execution: chunks are delete-and-reinsert, so reprocessing yields
    the same rows. Embedding failures are typed and leave the source
    failed/retryable (never bare exceptions).
    """
    source = await unit.sources.get(organization_id, project_id, source_id)
    if source is None:
        raise NotFoundError("source not found")

    await unit.sources.update_status(
        organization_id, project_id, source_id, status=STATUS_RUNNING, error=None
    )

    if not source.full_text or not source.full_text.strip():
        raise SourceProcessingError("source has no text to process")

    await _chunk_embed_complete(
        unit,
        organization_id=organization_id,
        project_id=project_id,
        source_id=source_id,
        full_text=source.full_text,
        notebook_id=source.notebook_id,
        embedder=embedder,
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
    "extract_file_text",
    "fail_text_source",
    "process_source",
    "process_text_source",
    "token_count",
]
