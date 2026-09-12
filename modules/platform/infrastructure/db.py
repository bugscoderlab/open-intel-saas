"""SQLAlchemy engine and Core table metadata for the platform schema.

The migrations in ``migrations/`` are the source of truth; these Core
tables mirror them for typed, composable queries. All access goes through
the repositories — no scattered client calls (plan §5.3).
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Table,
    Text,
    func,
)
from sqlalchemy import UUID as SAUUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

metadata = MetaData()

app_users = Table(
    "app_users",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("email", Text, nullable=False),
    Column("display_name", Text),
    Column("avatar_url", Text),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Column("last_sign_in_at", DateTime(timezone=True)),
)

user_identities = Table(
    "user_identities",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("app_user_id", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("auth_user_id", SAUUID),
    Column("provider", Text, nullable=False),
    Column("provider_subject", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

organizations = Table(
    "organizations",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("name", Text, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

organization_members = Table(
    "organization_members",
    metadata,
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), primary_key=True),
    Column("app_user_id", SAUUID, ForeignKey("app_users.id"), primary_key=True),
    Column("role", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

teams = Table(
    "teams",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

team_members = Table(
    "team_members",
    metadata,
    Column("team_id", SAUUID, ForeignKey("teams.id"), primary_key=True),
    Column("app_user_id", SAUUID, ForeignKey("app_users.id"), primary_key=True),
    Column("role", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

projects = Table(
    "projects",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("owning_team_id", SAUUID, ForeignKey("teams.id")),
    Column("name", Text, nullable=False),
    Column("visibility", Text, nullable=False),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

project_members = Table(
    "project_members",
    metadata,
    Column("project_id", SAUUID, ForeignKey("projects.id"), primary_key=True),
    Column("app_user_id", SAUUID, ForeignKey("app_users.id"), primary_key=True),
    Column("role", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

invitations = Table(
    "invitations",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("scope", Text, nullable=False),
    Column("team_id", SAUUID, ForeignKey("teams.id")),
    Column("project_id", SAUUID, ForeignKey("projects.id")),
    Column("email", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("token_hash", Text, nullable=False, unique=True),
    Column("invited_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

project_tags = Table(
    "project_tags",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("organization_id", SAUUID, ForeignKey("organizations.id"), nullable=False),
    Column("project_id", SAUUID, ForeignKey("projects.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("color", Text),
    Column("created_by", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Index("project_tags_project_name_key", "project_id", "name", unique=True),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("actor_id", SAUUID, ForeignKey("app_users.id"), nullable=False),
    Column("action", Text, nullable=False),
    Column("target_type", Text, nullable=False),
    Column("target_id", Text, nullable=False),
    Column("organization_id", SAUUID),
    Column("payload", JSON, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

outbox_events = Table(
    "outbox_events",
    metadata,
    Column("id", SAUUID, primary_key=True),
    Column("event_type", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), server_default=func.now()),
    Column("payload", JSON, nullable=False, server_default="{}"),
    Column("published_at", DateTime(timezone=True)),
)


def create_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(dsn, pool_size=5, max_overflow=5)


def create_session(engine: AsyncEngine) -> AsyncSession:
    return AsyncSession(engine, expire_on_commit=False)
