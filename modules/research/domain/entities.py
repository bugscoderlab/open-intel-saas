"""Research domain entities (spec #21) — pure dataclasses (plan §14.2).

The Notebook is the research container (glossary), inherited from Open
Notebook: it lives inside a Project and will eventually hold Sources.
Like every tenant-owned row it carries organization_id + project_id so
tenant filtering is explicit and auditable on the row itself.
"""

from dataclasses import dataclass
from uuid import UUID

# Source lifecycle (ticket #23). The API creates rows directly in
# "queued" — STATUS_NEW exists for later collection paths that stage a
# Source before submission. The SQL CHECK constraint on
# research.sources.status mirrors this set.
STATUS_NEW = "new"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
# 'file' widens the type set (ticket #29); the SQL CHECK constraint
# widened with migration 0013.
SOURCE_TYPES = ("text", "file")
SOURCE_STATUSES = (
    STATUS_NEW,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
SOURCE_TYPE_TEXT = "text"
SOURCE_TYPE_FILE = "file"


@dataclass(frozen=True)
class Notebook:
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    description: str | None
    archived: bool
    created_by: UUID


@dataclass(frozen=True)
class Source:
    """Anything ingested for study (glossary). Text path: full_text arrives
    with the create call; file path (ticket #29): the stored object's bytes
    arrive via the async pipeline, which extracts full_text off-request.
    notebook_id stays nullable per §9's source_chunks contract."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    notebook_id: UUID | None
    title: str
    type: str
    status: str
    full_text: str | None
    error: str | None
    created_by: UUID


@dataclass(frozen=True)
class SourceChunk:
    """A token-based slice of a Source's full_text, written by the async
    pipeline (delete-and-reinsert per run, mirroring upstream
    embed_source). Carries the tenant scope itself so chunk-level queries
    never need to join back to the source."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    notebook_id: UUID | None
    source_id: UUID
    chunk_index: int
    content: str
    # vector(EMBEDDING_DIMENSIONS), written by the pipeline's embedding
    # step (ticket #24); None only for rows written before 0010 / when
    # embedding is not yet configured.
    embedding: list[float] | None = None


@dataclass(frozen=True)
class SourceFile:
    """The registry row for a stored object (spec #26, plan §9.3): what was
    stored, where, and how big. Carries the tenant scope itself; the
    object key repeats it ({organization_id}/{project_id}/{source_id}/
    {filename}) so storage-level listing is also tenant-partitioned.
    Never stores a provider URL — downloads are signed at request time."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    source_id: UUID | None
    provider: str
    bucket: str
    object_key: str
    checksum: str
    size_bytes: int
    content_type: str
    created_by: UUID


@dataclass(frozen=True)
class SearchHit:
    """One search result (ticket #25). The shape is deliberately small:
    source id, title, snippet, score. Tenant scope never appears in a
    field — it is part of the query predicate, never a post-filter."""

    source_id: UUID
    title: str
    snippet: str
    score: float
