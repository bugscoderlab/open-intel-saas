"""SQLAlchemy Core table metadata for the research schema.

The migration (migrations/0006_research_notebooks.sql) is the source of
truth; this table mirrors it for typed, composable queries. The table
registers on the platform metadata so cross-schema foreign keys resolve;
no DDL is emitted from metadata — repositories only read/write.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import UUID as SAUUID
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    func,
)

from modules.platform.infrastructure.db import metadata

notebooks = Table(
    "notebooks",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column(
        "organization_id",
        SAUUID,
        ForeignKey("organizations.id"),
        nullable=False,
    ),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("archived", Boolean, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("notebooks_project_id_idx", "project_id"),
    Index("notebooks_organization_id_idx", "organization_id"),
    schema="research",
)

# Mirrors migrations/0008_research_sources.sql (the source of truth).
sources = Table(
    "sources",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column(
        "notebook_id", SAUUID, ForeignKey("research.notebooks.id"), nullable=True
    ),
    Column("title", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("full_text", Text),
    Column("error", Text),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("sources_project_id_idx", "project_id"),
    Index("sources_organization_id_idx", "organization_id"),
    Index("sources_notebook_id_idx", "notebook_id"),
    schema="research",
)

source_chunks = Table(
    "source_chunks",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column(
        "notebook_id", SAUUID, ForeignKey("research.notebooks.id"), nullable=True
    ),
    Column(
        "source_id", SAUUID, ForeignKey("research.sources.id"), nullable=False
    ),
    Column("chunk_index", Integer, nullable=False),
    Column("content", Text, nullable=False),
    # extensions.vector(1536) per plan §9; added by migration 0010.
    Column("embedding", Vector(1536), nullable=True),
    Index("source_chunks_project_id_idx", "project_id"),
    Index("source_chunks_organization_id_idx", "organization_id"),
    Index("source_chunks_source_id_idx", "source_id"),
    schema="research",
)

# Mirrors migrations/0012_research_source_files.sql (the source of truth).
# Registry of stored objects (plan §9.3): provider/bucket/object_key —
# never a provider URL.
source_files = Table(
    "source_files",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column(
        "source_id", SAUUID, ForeignKey("research.sources.id"), nullable=True
    ),
    Column("provider", Text, nullable=False),
    Column("bucket", Text, nullable=False),
    Column("object_key", Text, nullable=False),
    Column("checksum", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("content_type", Text, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("source_files_project_id_idx", "project_id"),
    Index("source_files_organization_id_idx", "organization_id"),
    Index("source_files_source_id_idx", "source_id"),
    schema="research",
)
