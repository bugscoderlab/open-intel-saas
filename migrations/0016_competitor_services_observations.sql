-- 0016: Competitor intelligence — service catalog + Observations
-- (ticket #34, spec #31, Phase 3 2/3).
--
-- Services are the canonical offering catalog, defined once per Project
-- (glossary) so price comparisons are apples-to-apples; the unique index
-- is case-insensitive on (project_id, name).
--
-- Observations are the stored, never-overwritten facts (glossary): one
-- row per observed value, with source reference arriving via evidence
-- links (ticket #35) and approval flow here. Approval states:
-- pending / approved / rejected / superseded. A new approved observation
-- with a different value for the same (competitor, service, location,
-- kind) supersedes the prior approved row and emits
-- CompetitorChangeDetected on the outbox (glossary: Change).

create table if not exists competitor.services (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    name text not null,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists services_project_lower_name_idx
    on competitor.services (project_id, lower(name));
create index if not exists services_organization_id_idx
    on competitor.services (organization_id);
create index if not exists services_project_id_idx
    on competitor.services (project_id);

create table if not exists competitor.observations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    competitor_id uuid not null
        references competitor.competitors (id) on delete cascade,
    service_id uuid
        references competitor.services (id) on delete restrict,
    location_id uuid
        references competitor.locations (id) on delete set null,
    kind text not null default 'price',
    price_amount numeric(12,2),
    price_currency text,
    observed_on date not null,
    confidence numeric(4,3) not null default 1.0,
    extraction_version text not null default 'manual-v1',
    approval_state text not null default 'pending'
        check (approval_state in ('pending', 'approved', 'rejected', 'superseded')),
    superseded_by uuid,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists observations_organization_id_idx
    on competitor.observations (organization_id);
create index if not exists observations_project_id_idx
    on competitor.observations (project_id);
create index if not exists observations_competitor_id_idx
    on competitor.observations (competitor_id);
create index if not exists observations_review_idx
    on competitor.observations (project_id, approval_state);

-- RLS safety net (plan §8.2), mirroring 0015.
alter table competitor.services enable row level security;
alter table competitor.observations enable row level security;

drop policy if exists services_member_all on competitor.services;
create policy services_member_all on competitor.services
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

drop policy if exists observations_member_all on competitor.observations;
create policy observations_member_all on competitor.observations
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

grant select on competitor.services to anon, authenticated;
grant select on competitor.observations to anon, authenticated;
