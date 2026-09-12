-- 0001: Application users and identities.
--
-- The product owns these tables; auth.users is never referenced by FK
-- (ticket #11 decision). One Application user per email; identities link
-- every provider subject to it. app_users.id mirrors nothing in Supabase
-- Auth — it is the stable identity all business tables reference.

create table if not exists public.app_users (
    id uuid primary key default gen_random_uuid(),
    email text not null,
    display_name text,
    avatar_url text,
    status text not null default 'pending'
        check (status in ('pending', 'active', 'disabled')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_sign_in_at timestamptz
);

-- Case-insensitive email uniqueness: one Application user per person.
create unique index if not exists app_users_email_lower_key
    on public.app_users (lower(email));

create table if not exists public.user_identities (
    id uuid primary key default gen_random_uuid(),
    app_user_id uuid not null
        references public.app_users (id) on delete cascade,
    auth_user_id uuid,
    provider text not null,
    provider_subject text not null,
    created_at timestamptz not null default now(),
    unique (provider, provider_subject)
);

create index if not exists user_identities_app_user_id_idx
    on public.user_identities (app_user_id);
create index if not exists user_identities_auth_user_id_idx
    on public.user_identities (auth_user_id);
