-- 0017: Competitor intelligence — Evidence links (ticket #35, spec #31,
-- Phase 3 3/3).
--
-- Evidence connects a Competitor (and optionally one of its
-- Observations) to a research Source OR Notebook. Target IDs stay
-- opaque UUIDs — no foreign key into research (plan §14.4 rule 2;
-- research is an optional dependency) — and cross-module existence
-- validation is deliberately deferred until Phase 5 (spec #31
-- assumption 4, behind the module-enabled check). Deleting an
-- observation retains the link on the competitor (observation_id
-- nulls via ON DELETE SET NULL).

create table if not exists competitor.evidence_links (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    competitor_id uuid not null
        references competitor.competitors (id) on delete cascade,
    observation_id uuid
        references competitor.observations (id) on delete set null,
    target_kind text not null
        check (target_kind in ('source', 'notebook')),
    target_id uuid not null,
    excerpt text,
    excerpt_start integer,
    excerpt_end integer,
    approval_state text not null default 'approved'
        check (approval_state in ('pending', 'approved', 'rejected')),
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (excerpt_end >= excerpt_start)
);

create index if not exists evidence_links_organization_id_idx
    on competitor.evidence_links (organization_id);
create index if not exists evidence_links_project_id_idx
    on competitor.evidence_links (project_id);
create index if not exists evidence_links_competitor_id_idx
    on competitor.evidence_links (competitor_id);
create index if not exists evidence_links_observation_id_idx
    on competitor.evidence_links (observation_id);
create index if not exists evidence_links_target_idx
    on competitor.evidence_links (target_kind, target_id);

-- RLS safety net (plan §8.2), mirroring 0015/0016.
alter table competitor.evidence_links enable row level security;

drop policy if exists evidence_links_member_all on competitor.evidence_links;
create policy evidence_links_member_all on competitor.evidence_links
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

grant select on competitor.evidence_links to anon, authenticated;
