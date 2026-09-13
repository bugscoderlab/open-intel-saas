-- 0012: Research module — source file registry (ticket #28, spec #26,
-- Phase 2 backfill 1/3).
--
-- Plan §9.3: files live under tenant-scoped object keys
-- (organization-id/project-id/source-id/filename); the database stores
-- provider/bucket/object_key/checksum — never a provider URL. Signed
-- download URLs are generated at request time, only after authorization.
-- source_id is nullable: the registry is a generic stored-object table
-- (ticket #29 links file sources; later phases store snapshots/evidence).

create table if not exists research.source_files (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    source_id uuid
        references research.sources (id) on delete cascade,
    provider text not null,
    bucket text not null,
    object_key text not null,
    checksum text not null,
    size_bytes bigint not null,
    content_type text not null,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now()
);

create index if not exists source_files_organization_id_idx
    on research.source_files (organization_id);
create index if not exists source_files_project_id_idx
    on research.source_files (project_id);
create index if not exists source_files_source_id_idx
    on research.source_files (source_id);

-- RLS safety net (plan §8.2): mirrors the research.sources pattern so a
-- repository-layer bug still cannot leak across tenants when the caller
-- connects as the authenticated role with the user JWT.
alter table research.source_files enable row level security;

drop policy if exists source_files_member_all on research.source_files;
create policy source_files_member_all on research.source_files
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

-- Dedicated-schema grant gap (same as 0007/0009): the API connects as the
-- schema owner; SELECT is all the authenticated role needs, with row
-- access governed entirely by the policy above.
grant select on research.source_files to anon, authenticated;
