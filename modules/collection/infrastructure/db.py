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

# A job is a collection SCHEDULE (ticket #44): the scheduler claims it
# when enabled and next_due_at <= now, creating a job_run plus a
# CollectionDue outbox event in the same transaction (ADR-004). The
# status/snapshot_id/error columns are #42 leftovers, unused since
# attempts moved to job_runs (expand/contract; drop is Phase 5).
jobs = Table(
    "jobs",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("competitor_id", SAUUID, nullable=False),
    Column("connector_kind", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("interval_seconds", Integer, nullable=True),
    Column("next_due_at", DateTime(timezone=True), nullable=True),
    Column("enabled", Boolean, nullable=False, server_default="true"),
    Column("failures", Integer, nullable=False, server_default="0"),
    Column("status", Text, nullable=False),
    Column("snapshot_id", SAUUID, ForeignKey("collection.snapshots.id"), nullable=True),
    Column("error", Text),
    Column("requested_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("jobs_organization_id_idx", "organization_id"),
    Index("jobs_pending_idx", "project_id", "status", "created_at"),
    Index("jobs_quota_idx", "project_id", "created_at"),
    Index("jobs_due_idx", "enabled", "next_due_at"),
    schema="collection",
)

# One row per collection attempt (scheduled or ad-hoc), mirroring
# migrations/0020_collection_schedules_job_runs.sql.
job_runs = Table(
    "job_runs",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("job_id", SAUUID, ForeignKey("collection.jobs.id"), nullable=True),
    Column("competitor_id", SAUUID, nullable=False),
    Column("connector_kind", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("snapshot_id", SAUUID, ForeignKey("collection.snapshots.id"), nullable=True),
    Column("error", Text),
    Column("attempt", Integer, nullable=False, server_default="0"),
    Column("requested_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("run_at", DateTime(timezone=True), server_default=func.now()),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Index("job_runs_organization_id_idx", "organization_id"),
    Index("job_runs_pending_idx", "status", "run_at"),
    Index("job_runs_job_id_idx", "job_id"),
    Index("job_runs_quota_idx", "project_id", "run_at"),
    schema="collection",
)
