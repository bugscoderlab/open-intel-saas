-- 0008: Research module — Sources + source chunks (ticket #23, spec #21).
--
-- Assumes 0006 created the research schema (migrations run in numeric
-- order, each in one transaction).
--
-- Bullet 2/4 of the research tracer bullet: an Application user pastes text
-- into a Notebook and the system ingests it as a Source, processed
-- asynchronously off-request (ADR-004). The shape copies the notebook
-- tenancy pattern: every row carries organization_id + project_id, and
-- notebook_id stays nullable per §9's source_chunks contract (a Source is
-- not forced to live inside a Notebook). source_chunks carries the text
-- chunks the async pipeline writes (delete-and-reinsert on retry, mirroring
-- upstream embed_source semantics); the embedding column lands with ticket
-- #24 (embeddings).

create table if not exists research.sources (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    notebook_id uuid
        references research.notebooks (id) on delete cascade,
    title text not null,
    type text not null default 'text' check (type in ('text')),
    status text not null default 'queued'
        check (status in ('new', 'queued', 'running', 'completed', 'failed')),
    full_text text,
    error text,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists sources_organization_id_idx
    on research.sources (organization_id);
create index if not exists sources_project_id_idx
    on research.sources (project_id);
create index if not exists sources_notebook_id_idx
    on research.sources (notebook_id);

-- RLS safety net (plan §8.2): mirrors the platform pattern so a
-- repository-layer bug still cannot leak across tenants when the caller
-- connects as the authenticated role with the user JWT.
alter table research.sources enable row level security;

drop policy if exists sources_member_all on research.sources;
create policy sources_member_all on research.sources
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

create table if not exists research.source_chunks (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    notebook_id uuid
        references research.notebooks (id) on delete cascade,
    source_id uuid not null
        references research.sources (id) on delete cascade,
    chunk_index integer not null,
    content text not null
);

create index if not exists source_chunks_organization_id_idx
    on research.source_chunks (organization_id);
create index if not exists source_chunks_project_id_idx
    on research.source_chunks (project_id);
create index if not exists source_chunks_source_id_idx
    on research.source_chunks (source_id);

alter table research.source_chunks enable row level security;

drop policy if exists source_chunks_member_all on research.source_chunks;
create policy source_chunks_member_all on research.source_chunks
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));
