-- 0014: Research module — Notes (ticket #30, spec #26, Phase 2 backfill 3/3).
--
-- A Note belongs to a Notebook (upstream semantics; spec #26 assumption 4)
-- and carries the tenant scope like every research row: organization_id +
-- project_id on the row itself, mirroring the notebooks pattern (0006).
-- Deleting a Notebook cascades to its Notes.

create table if not exists research.notes (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    notebook_id uuid not null
        references research.notebooks (id) on delete cascade,
    title text not null,
    content text not null default '',
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists notes_organization_id_idx
    on research.notes (organization_id);
create index if not exists notes_project_id_idx
    on research.notes (project_id);
create index if not exists notes_notebook_id_idx
    on research.notes (notebook_id);

-- RLS safety net (plan §8.2): mirrors the research.sources pattern so a
-- repository-layer bug still cannot leak across tenants when the caller
-- connects as the authenticated role with the user JWT.
alter table research.notes enable row level security;

drop policy if exists notes_member_all on research.notes;
create policy notes_member_all on research.notes
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

-- Dedicated-schema grant gap (same as 0009/0012).
grant select on research.notes to anon, authenticated;
