"""SQLAlchemy Core table metadata for the competitor schema.

Mirrors migrations/0015_competitor_directory.sql (the source of truth);
registers on the platform metadata so cross-schema foreign keys resolve.
No DDL is emitted from metadata — repositories only read/write.
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

competitors = Table(
    "competitors",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("website", Text),
    Column("notes", Text),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("competitors_project_id_idx", "project_id"),
    Index("competitors_organization_id_idx", "organization_id"),
    schema="competitor",
)

locations = Table(
    "locations",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column(
        "competitor_id",
        SAUUID,
        ForeignKey("competitor.competitors.id"),
        nullable=False,
    ),
    Column("name", Text, nullable=False),
    Column("address", Text),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("locations_project_id_idx", "project_id"),
    Index("locations_organization_id_idx", "organization_id"),
    Index("locations_competitor_id_idx", "competitor_id"),
    schema="competitor",
)
