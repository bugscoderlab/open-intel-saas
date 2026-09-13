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
SOURCE_TYPES = ("text",)
SOURCE_STATUSES = (
    STATUS_NEW,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
SOURCE_TYPE_TEXT = "text"


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
    """Anything ingested for study (glossary). Text path for this bullet:
    full_text arrives with the create call, the async pipeline chunks it.
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
