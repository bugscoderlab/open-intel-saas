-- 0018: Collection — website snapshots + collection jobs (ticket #42,
-- spec #41, Phase 4 1/3).
--
-- Snapshots are the raw captures behind competitor intelligence
-- (glossary: Snapshot). Content is sha256-deduped per competitor +
-- connector: a re-collection whose hash matches the latest snapshot
-- writes no row (the job still records "unchanged"), changed content
-- writes a NEW row — snapshots are retained forever and never
-- overwritten, and the last successful snapshot survives later failed
-- runs. competitor_id is a deliberately opaque UUID: collection is an
-- independent module (plan §14.4) and cross-module existence
-- validation is deferred to Phase 5, mirroring competitor.evidence_links.

create schema if not exists collection;

create table if not exists collection.snapshots (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    competitor_id uuid not null,
    connector_kind text not null
        check (connector_kind in ('website')),
    url text not null,
    content_hash text not null,
    raw_payload text not null,
    captured_at timestamptz not null,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now()
);

create index if not exists snapshots_organization_id_idx
    on collection.snapshots (organization_id);
create index if not exists snapshots_project_id_idx
    on collection.snapshots (project_id);
-- Latest-snapshot lookup for hash dedup, newest first for listing.
create index if not exists snapshots_competitor_idx
    on collection.snapshots (project_id, competitor_id, connector_kind, captured_at desc);

-- A job is one collection attempt. POST creates it "pending" plus a
-- CollectionJobRequested outbox event in one transaction (PDR-003);
-- the dispatcher drains it off-request (ADR-004 pattern). The result
-- stays on the row: snapshot_created / unchanged / failed. The per-
-- project fetch quota counts jobs created in the last 24 hours.
create table if not exists collection.jobs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    competitor_id uuid not null,
    connector_kind text not null
        check (connector_kind in ('website')),
    url text not null,
    status text not null default 'pending'
        check (status in ('pending', 'snapshot_created', 'unchanged', 'failed')),
    snapshot_id uuid
        references collection.snapshots (id) on delete set null,
    error text,
    requested_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists jobs_organization_id_idx
    on collection.jobs (organization_id);
create index if not exists jobs_pending_idx
    on collection.jobs (project_id, status, created_at);
create index if not exists jobs_quota_idx
    on collection.jobs (project_id, created_at);

-- RLS safety net (plan §8.2), mirroring 0015-0017.
alter table collection.snapshots enable row level security;
alter table collection.jobs enable row level security;

drop policy if exists snapshots_member_all on collection.snapshots;
create policy snapshots_member_all on collection.snapshots
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

drop policy if exists jobs_member_all on collection.jobs;
create policy jobs_member_all on collection.jobs
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

grant select on collection.snapshots to anon, authenticated;
grant select on collection.jobs to anon, authenticated;
