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
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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

# Mirrors migrations/0016_competitor_services_observations.sql.
services = Table(
    "services",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("services_project_id_idx", "project_id"),
    Index("services_organization_id_idx", "organization_id"),
    schema="competitor",
)

observations = Table(
    "observations",
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
    Column(
        "service_id",
        SAUUID,
        ForeignKey("competitor.services.id"),
        nullable=True,
    ),
    Column(
        "location_id",
        SAUUID,
        ForeignKey("competitor.locations.id"),
        nullable=True,
    ),
    Column("kind", Text, nullable=False),
    Column("price_amount", Numeric(12, 2)),
    Column("price_currency", Text),
    Column("observed_on", Date, nullable=False),
    Column("confidence", Numeric(4, 3), nullable=False),
    Column("extraction_version", Text, nullable=False),
    Column("approval_state", Text, nullable=False),
    Column("superseded_by", SAUUID, nullable=True),
    # Extraction metadata (ticket #56) — see migration 0022.
    Column("claim", Text, nullable=True),
    Column("sentiment", Text, nullable=True),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("observations_project_id_idx", "project_id"),
    Index("observations_organization_id_idx", "organization_id"),
    Index("observations_competitor_id_idx", "competitor_id"),
    Index("observations_review_idx", "project_id", "approval_state"),
    schema="competitor",
)

# Mirrors migrations/0017_competitor_evidence_links.sql. Target IDs are
# opaque UUIDs — deliberately no FK into research (plan §14.4 rule 2).
evidence_links = Table(
    "evidence_links",
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
    Column(
        "observation_id",
        SAUUID,
        ForeignKey("competitor.observations.id"),
        nullable=True,
    ),
    Column("target_kind", Text, nullable=False),
    Column("target_id", SAUUID, nullable=False),
    Column("excerpt", Text),
    Column("excerpt_start", Integer),
    Column("excerpt_end", Integer),
    Column("approval_state", Text, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("evidence_links_project_id_idx", "project_id"),
    Index("evidence_links_organization_id_idx", "organization_id"),
    Index("evidence_links_competitor_id_idx", "competitor_id"),
    Index("evidence_links_observation_id_idx", "observation_id"),
    Index("evidence_links_target_idx", "target_kind", "target_id"),
    schema="competitor",
)
