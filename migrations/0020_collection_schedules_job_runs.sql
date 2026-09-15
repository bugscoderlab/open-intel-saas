-- 0020: Collection — schedules on jobs + job_runs attempts table
-- (ticket #44, spec #41, Phase 4 3/3).
--
-- #42 shipped `collection.jobs` as one row per ATTEMPT. This migration
-- lands the spec #41 model: jobs are SCHEDULES (interval + next due
-- time, enabled flag, consecutive-failure counter for backoff), and
-- attempts move to `collection.job_runs` (ad-hoc on-demand runs have
-- job_id NULL). The jobs status/error/snapshot_id columns from #42 are
-- left in place but unused — expand/contract; their drop is Phase 5
-- cleanup material.

alter table collection.jobs
    add column if not exists interval_seconds integer,
    add column if not exists next_due_at timestamptz,
    add column if not exists enabled boolean not null default true,
    add column if not exists failures integer not null default 0;

create table if not exists collection.job_runs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    job_id uuid
        references collection.jobs (id) on delete set null,
    competitor_id uuid not null,
    connector_kind text not null
        check (connector_kind in ('website')),
    url text not null,
    status text not null default 'pending'
        check (status in ('pending', 'snapshot_created', 'unchanged', 'failed')),
    snapshot_id uuid
        references collection.snapshots (id) on delete set null,
    error text,
    -- Attempt number within the schedule's current failure streak
    -- (0 for a scheduled run that followed a success / first run).
    attempt integer not null default 0,
    requested_by uuid not null references public.app_users (id),
    run_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists job_runs_organization_id_idx
    on collection.job_runs (organization_id);
create index if not exists job_runs_pending_idx
    on collection.job_runs (status, run_at);
create index if not exists job_runs_job_id_idx
    on collection.job_runs (job_id);
-- Quota counting (jobs created in the last 24h, per project).
create index if not exists job_runs_quota_idx
    on collection.job_runs (project_id, run_at);
-- Schedule listing per competitor.
create index if not exists jobs_due_idx
    on collection.jobs (enabled, next_due_at);

-- RLS safety net (plan §8.2), mirroring 0018.
alter table collection.job_runs enable row level security;

drop policy if exists job_runs_member_all on collection.job_runs;
create policy job_runs_member_all on collection.job_runs
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

grant select on collection.job_runs to anon, authenticated;
