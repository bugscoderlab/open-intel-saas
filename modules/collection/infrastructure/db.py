"""SQLAlchemy Core table metadata for the collection schema.

Mirrors migrations/0018_collection_snapshots_jobs.sql (the source of
truth); registers on the platform metadata so cross-schema foreign keys
resolve (organizations/projects/app_users live in public). No DDL is
emitted from metadata — repositories only read/write. competitor_id is
a plain UUID column: collection is an independent module and never
foreign-keys into competitor (plan §14.4, mirroring evidence_links).
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
)

from modules.platform.infrastructure.db import metadata

snapshots = Table(
    "snapshots",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("competitor_id", SAUUID, nullable=False),
    Column("connector_kind", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("raw_payload", Text, nullable=False),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("snapshots_project_id_idx", "project_id"),
    Index("snapshots_organization_id_idx", "organization_id"),
    Index(
        "snapshots_competitor_idx",
        "project_id",
        "competitor_id",
        "connector_kind",
        "captured_at",
    ),
    schema="collection",
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("competitor_id", SAUUID, nullable=False),
    Column("connector_kind", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("snapshot_id", SAUUID, ForeignKey("collection.snapshots.id"), nullable=True),
    Column("error", Text),
    Column("requested_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("jobs_organization_id_idx", "organization_id"),
    Index("jobs_pending_idx", "project_id", "status", "created_at"),
    Index("jobs_quota_idx", "project_id", "created_at"),
    schema="collection",
)
