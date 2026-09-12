-- 0005: Deletion behavior for creator/actor references.
--
-- Account deletion (public.remove_app_user_on_auth_user_delete) removes the
-- Application user row; every reference must survive that gracefully.
-- Membership tables cascade (a removed user loses memberships — correct).
-- Creator/actor references are set to NULL: tenant data outlives its
-- creator, and the audit trail anonymizes rather than blocking deletion.

alter table public.organizations
    alter column created_by drop not null;
alter table public.organizations
    drop constraint organizations_created_by_fkey;
alter table public.organizations
    add constraint organizations_created_by_fkey
    foreign key (created_by) references public.app_users (id) on delete set null;

alter table public.teams
    alter column created_by drop not null;
alter table public.teams
    drop constraint teams_created_by_fkey;
alter table public.teams
    add constraint teams_created_by_fkey
    foreign key (created_by) references public.app_users (id) on delete set null;

alter table public.projects
    alter column created_by drop not null;
alter table public.projects
    drop constraint projects_created_by_fkey;
alter table public.projects
    add constraint projects_created_by_fkey
    foreign key (created_by) references public.app_users (id) on delete set null;

alter table public.project_tags
    alter column created_by drop not null;
alter table public.project_tags
    drop constraint project_tags_created_by_fkey;
alter table public.project_tags
    add constraint project_tags_created_by_fkey
    foreign key (created_by) references public.app_users (id) on delete set null;

alter table public.invitations
    alter column invited_by drop not null;
alter table public.invitations
    drop constraint invitations_invited_by_fkey;
alter table public.invitations
    add constraint invitations_invited_by_fkey
    foreign key (invited_by) references public.app_users (id) on delete set null;

alter table public.audit_log
    alter column actor_id drop not null;
alter table public.audit_log
    drop constraint audit_log_actor_id_fkey;
alter table public.audit_log
    add constraint audit_log_actor_id_fkey
    foreign key (actor_id) references public.app_users (id) on delete set null;
