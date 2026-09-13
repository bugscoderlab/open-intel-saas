-- 0006: Research module — Notebook (ticket #22, spec #21).
--
-- First table of modules/research, in the module's own schema per plan
-- §14.4 (schema-per-module; cross-module FKs only to stable platform IDs).
-- The shape copies the platform tenancy pattern: every row carries
-- organization_id + project_id.

create schema if not exists research;

create table if not exists research.notebooks (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    name text not null,
    description text,
    archived boolean not null default false,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists notebooks_organization_id_idx
    on research.notebooks (organization_id);
create index if not exists notebooks_project_id_idx
    on research.notebooks (project_id);

-- RLS safety net (plan §8.2): mirrors the platform pattern so a
-- repository-layer bug still cannot leak across tenants when the caller
-- connects as the authenticated role with the user JWT.
alter table research.notebooks enable row level security;

drop policy if exists notebooks_member_all on research.notebooks;
create policy notebooks_member_all on research.notebooks
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));
