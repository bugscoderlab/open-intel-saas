-- 0015: Competitor intelligence — schema, competitors, locations
-- (ticket #33, spec #31, Phase 3 1/3).
--
-- First business feature module (plan §14.4: the module owns the
-- competitor.* schema; every tenant-owned row carries organization_id +
-- project_id). A Competitor belongs to a Project — which IS a Market
-- when configured for competitor intelligence (glossary), so the same
-- real-world business is a separate record per market (deliberate).

create schema if not exists competitor;

create table if not exists competitor.competitors (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    name text not null,
    website text,
    notes text,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists competitors_organization_id_idx
    on competitor.competitors (organization_id);
create index if not exists competitors_project_id_idx
    on competitor.competitors (project_id);

create table if not exists competitor.locations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    competitor_id uuid not null
        references competitor.competitors (id) on delete cascade,
    name text not null,
    address text,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists locations_organization_id_idx
    on competitor.locations (organization_id);
create index if not exists locations_project_id_idx
    on competitor.locations (project_id);
create index if not exists locations_competitor_id_idx
    on competitor.locations (competitor_id);

-- RLS safety net (plan §8.2): mirrors the research pattern so a
-- repository-layer bug still cannot leak across tenants when the caller
-- connects as the authenticated role with the user JWT.
alter table competitor.competitors enable row level security;
alter table competitor.locations enable row level security;

drop policy if exists competitors_member_all on competitor.competitors;
create policy competitors_member_all on competitor.competitors
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

drop policy if exists locations_member_all on competitor.locations;
create policy locations_member_all on competitor.locations
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

-- Dedicated-schema grants (same gap as research 0007/0009): the API
-- connects as the schema owner; SELECT is all the authenticated role
-- needs, with row access governed by the policies above.
grant usage on schema competitor to anon, authenticated;
grant select on competitor.competitors to anon, authenticated;
grant select on competitor.locations to anon, authenticated;
