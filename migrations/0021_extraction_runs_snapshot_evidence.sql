-- 0021: Extraction — extraction_runs + snapshot evidence target
-- (ticket #50, spec #47, Phase 5 2/3).
--
-- One row per extraction attempt over one collection snapshot, enqueued
-- through the outbox (ADR-004) and drained off-request. Status carries
-- pending/succeeded/failed; the extraction_version marker ties the run
-- to the prompt+schema contract (extract-v1…) so re-derivation after a
-- version bump is auditable.
--
-- The evidence_links target_kind check constraint widens to accept
-- 'snapshot' — deferred to Phase 5 per the phase-3 domain comment.

create schema if not exists extraction;

create table if not exists extraction.extraction_runs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    competitor_id uuid not null,
    snapshot_id uuid not null,
    status text not null default 'pending'
        check (status in ('pending', 'succeeded', 'failed')),
    extraction_version text not null,
    error text,
    requested_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists extraction_runs_pending_idx
    on extraction.extraction_runs (created_at)
    where status = 'pending';

-- Request-level idempotency: one active/successful run per
-- (snapshot, extraction_version).
create unique index if not exists extraction_runs_snapshot_version_idx
    on extraction.extraction_runs (project_id, snapshot_id, extraction_version)
    where status in ('pending', 'succeeded');

-- expand/contract: add the new allowed kind before enforcing it
alter table competitor.evidence_links drop constraint if exists
    evidence_links_target_kind_check;

alter table competitor.evidence_links
    add constraint evidence_links_target_kind_check
    check (target_kind in ('source', 'notebook', 'snapshot'));
