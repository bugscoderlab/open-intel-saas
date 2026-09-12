-- 0002: Platform tenancy schema — Organization, Team, Project, membership,
-- invitations, Project tags, audit log, outbox (ticket #11).
--
-- Every tenant-owned row carries organization_id; project-owned rows also
-- carry project_id. This pair is the tenant-scoping pattern every later
-- module copies (plan §9).

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.organization_members (
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    app_user_id uuid not null
        references public.app_users (id) on delete cascade,
    role text not null check (role in ('owner', 'admin', 'member')),
    created_at timestamptz not null default now(),
    primary key (organization_id, app_user_id)
);

create index if not exists organization_members_app_user_id_idx
    on public.organization_members (app_user_id);

create table if not exists public.teams (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    name text not null,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists teams_organization_id_idx
    on public.teams (organization_id);

create table if not exists public.team_members (
    team_id uuid not null
        references public.teams (id) on delete cascade,
    app_user_id uuid not null
        references public.app_users (id) on delete cascade,
    role text not null check (role in ('manager', 'member')),
    created_at timestamptz not null default now(),
    primary key (team_id, app_user_id)
);

create index if not exists team_members_app_user_id_idx
    on public.team_members (app_user_id);

create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    owning_team_id uuid
        references public.teams (id) on delete set null,
    name text not null,
    visibility text not null default 'private'
        check (visibility in ('private', 'team', 'organization')),
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists projects_organization_id_idx
    on public.projects (organization_id);
create index if not exists projects_owning_team_id_idx
    on public.projects (owning_team_id);

create table if not exists public.project_members (
    project_id uuid not null
        references public.projects (id) on delete cascade,
    app_user_id uuid not null
        references public.app_users (id) on delete cascade,
    role text not null check (role in ('editor', 'viewer')),
    created_at timestamptz not null default now(),
    primary key (project_id, app_user_id)
);

create index if not exists project_members_app_user_id_idx
    on public.project_members (app_user_id);

-- App-level invitations: no auth.users row is touched at invite time
-- (ticket #6 decision). The raw token exists only in the emailed link;
-- only its hash is stored here.
create table if not exists public.invitations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    scope text not null
        check (scope in ('organization', 'team', 'project')),
    team_id uuid references public.teams (id) on delete cascade,
    project_id uuid references public.projects (id) on delete cascade,
    email text not null,
    role text not null,
    token_hash text not null unique,
    invited_by uuid not null references public.app_users (id),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    created_at timestamptz not null default now(),
    check (
        (scope = 'organization' and team_id is null and project_id is null)
        or (scope = 'team' and team_id is not null and project_id is null)
        or (scope = 'project' and project_id is not null and team_id is null)
    )
);

create index if not exists invitations_organization_id_idx
    on public.invitations (organization_id);

-- The trivial tenant-owned entity proving the scoping pattern (ticket #8).
create table if not exists public.project_tags (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null
        references public.organizations (id) on delete cascade,
    project_id uuid not null
        references public.projects (id) on delete cascade,
    name text not null,
    color text,
    created_by uuid not null references public.app_users (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (project_id, name)
);

create index if not exists project_tags_organization_id_idx
    on public.project_tags (organization_id);

-- Audit: every mutating platform action, never reads (ticket #8 decision).
create table if not exists public.audit_log (
    id bigserial primary key,
    actor_id uuid not null references public.app_users (id),
    action text not null,
    target_type text not null,
    target_id text not null,
    organization_id uuid,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists audit_log_organization_id_idx
    on public.audit_log (organization_id);
create index if not exists audit_log_created_at_idx
    on public.audit_log (created_at);

-- Transactional outbox: the event envelope is defined from day one
-- (ticket #8 decision). The dispatcher arrives with the first consumer.
create table if not exists public.outbox_events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    published_at timestamptz
);

create index if not exists outbox_events_unpublished_idx
    on public.outbox_events (occurred_at)
    where published_at is null;
