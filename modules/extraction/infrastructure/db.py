"""SQLAlchemy Core table metadata for the extraction schema.

Mirrors migrations/0021_extraction_runs_snapshot_evidence.sql (the
source of truth); registers on the platform metadata so cross-schema
foreign keys resolve. No DDL is emitted from metadata — repositories
only read/write. snapshot_id is a plain UUID column: extraction is an
independent module and never foreign-keys into collection (plan §14.4).
"""

from sqlalchemy import (
    UUID as SAUUID,
)
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Table,
    Text,
    func,
    text,
)

from modules.platform.infrastructure.db import metadata

extraction_runs = Table(
    "extraction_runs",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("competitor_id", SAUUID, nullable=False),
    Column("snapshot_id", SAUUID, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("extraction_version", Text, nullable=False),
    Column("error", Text, nullable=True),
    Column("requested_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Index("extraction_runs_project_id_idx", "project_id"),
    Index("extraction_runs_organization_id_idx", "organization_id"),
    Index(
        "extraction_runs_pending_idx",
        "created_at",
        postgresql_where=text("status = 'pending'"),
    ),
    Index(
        "extraction_runs_snapshot_version_idx",
        "project_id",
        "snapshot_id",
        "extraction_version",
        unique=True,
        postgresql_where=text("status in ('pending', 'succeeded')"),
    ),
    schema="extraction",
)
