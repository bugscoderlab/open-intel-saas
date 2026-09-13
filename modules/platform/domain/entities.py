"""Tenant-owned domain entities: pure dataclasses (plan §14.2).

Every record carries its tenant scope (``organization_id``, plus
``project_id`` where project-owned) so tenant filtering is explicit and
auditable on the row itself.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class AppUser:
    id: UUID
    email: str
    display_name: str | None
    status: str


@dataclass(frozen=True)
class Organization:
    id: UUID
    name: str
    created_by: UUID


@dataclass(frozen=True)
class Membership:
    organization_id: UUID
    app_user_id: UUID
    role: str  # owner | admin | member


@dataclass(frozen=True)
class Team:
    id: UUID
    organization_id: UUID
    name: str
    created_by: UUID


@dataclass(frozen=True)
class TeamMembership:
    team_id: UUID
    app_user_id: UUID
    role: str  # manager | member


@dataclass(frozen=True)
class Project:
    id: UUID
    organization_id: UUID
    owning_team_id: UUID | None
    name: str
    visibility: str  # private | team | organization
    created_by: UUID


@dataclass(frozen=True)
class ProjectMembership:
    project_id: UUID
    app_user_id: UUID
    role: str  # editor | viewer


@dataclass(frozen=True)
class ProjectTag:
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    color: str | None
    created_by: UUID


@dataclass(frozen=True)
class Invitation:
    id: UUID
    organization_id: UUID
    scope: str  # organization | team | project
    team_id: UUID | None
    project_id: UUID | None
    email: str
    role: str
    token_hash: str
    invited_by: UUID
    expires_at: datetime
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class AuditEntry:
    actor_id: UUID
    action: str
    target_type: str
    target_id: str
    organization_id: UUID | None
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OutboxEvent:
    event_type: str
    payload: dict


@dataclass(frozen=True)
class OutboxEventRecord:
    """A persisted outbox row as consumed by dispatchers: the database id
    plus what was written. ``add`` takes an OutboxEvent (no id — the
    database assigns it); readers get records back."""

    id: UUID
    event_type: str
    payload: dict
