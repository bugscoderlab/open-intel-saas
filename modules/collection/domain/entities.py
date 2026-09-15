"""Collection domain entities (spec #41) — pure dataclasses (plan §14.2).

A Snapshot is one raw capture of a competitor's web presence. A Job is
a SCHEDULE: competitor + connector + interval, claimed by the scheduler
when due (glossary: Collection job). A JobRun is one collection attempt
— ad-hoc on-demand runs have no schedule (job_id None). Tenant-owned
rows carry organization_id + project_id like every other module's rows;
competitor_id is a deliberately opaque UUID — collection never imports
the competitor module and existence validation is deferred to Phase 5
(spec #41, mirroring competitor.evidence_links).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# The only connector in Phase 4; maps discovery (#43) returns data only
# and scheduled fetches reuse the website pipeline.
CONNECTOR_WEBSITE = "website"
CONNECTOR_KINDS = (CONNECTOR_WEBSITE,)

# JobRun lifecycle: created "pending"; the drain records one of the
# three terminal outcomes. "unchanged" means the fetched content hashed
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
    """A collection schedule. The scheduler claims it when ``enabled``
    and ``next_due_at <= now``; ``failures`` counts the current
    consecutive-failure streak and drives the retry backoff."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    connector_kind: str
    url: str
    interval_seconds: int
    next_due_at: datetime
    enabled: bool
    failures: int
    created_by: UUID


@dataclass(frozen=True)
class JobRun:
    """One collection attempt (scheduled or ad-hoc). Records the
    outcome, the typed error on failure, and the attempt number within
    the schedule's failure streak."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    job_id: UUID | None
    competitor_id: UUID
    connector_kind: str
    url: str
    status: str
    snapshot_id: UUID | None
    error: str | None
    attempt: int
    requested_by: UUID
    run_at: datetime
    finished_at: datetime | None
