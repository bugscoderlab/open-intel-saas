"""Collection domain entities (spec #41) — pure dataclasses (plan §14.2).

A Snapshot is one raw capture of a competitor's web presence; a Job is
one collection attempt (glossary: Collection job). Tenant-owned rows
carry organization_id + project_id like every other module's rows;
competitor_id is a deliberately opaque UUID — collection never imports
the competitor module and existence validation is deferred to Phase 5
(spec #41, mirroring competitor.evidence_links).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# The only connector in Phase 4 1/3; maps discovery (#43) and scheduled
# jobs (#44) add kinds behind the same tables.
CONNECTOR_WEBSITE = "website"
CONNECTOR_KINDS = (CONNECTOR_WEBSITE,)

# Job lifecycle: POST lands "pending"; the drain records one of the
# three terminal results. "unchanged" means the fetched content hashed
# equal to the competitor's latest snapshot — no new row was written.
JOB_PENDING = "pending"
JOB_SNAPSHOT_CREATED = "snapshot_created"
JOB_UNCHANGED = "unchanged"
JOB_FAILED = "failed"
JOB_STATES = (
    JOB_PENDING,
    JOB_SNAPSHOT_CREATED,
    JOB_UNCHANGED,
    JOB_FAILED,
)


@dataclass(frozen=True)
class Snapshot:
    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    connector_kind: str
    url: str
    content_hash: str
    raw_payload: str
    captured_at: datetime
    created_by: UUID


@dataclass(frozen=True)
class Job:
    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    connector_kind: str
    url: str
    status: str
    snapshot_id: UUID | None
    error: str | None
    requested_by: UUID
