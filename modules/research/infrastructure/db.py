"""SQLAlchemy Core table metadata for the research schema.

The migration (migrations/0006_research_notebooks.sql) is the source of
truth; this table mirrors it for typed, composable queries. The table
registers on the platform metadata so cross-schema foreign keys resolve;
no DDL is emitted from metadata — repositories only read/write.
"""

from sqlalchemy import UUID as SAUUID
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
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
