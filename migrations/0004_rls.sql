-- 0004: Row-level security — the independent safety net (ticket #11, plan §8.2).
--
-- Repositories are the enforced layer and always filter by tenant scope;
-- these policies exist so a bug there still cannot leak across tenants
-- when the caller connects as the authenticated role with the user JWT.
-- The backend's service connection bypasses RLS and must therefore keep
-- applying explicit tenant filters itself.

-- Map the JWT subject (auth user id) to the Application user id through
-- user_identities — the same resolution the API layer performs.
create or replace function public.current_app_user_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
    select ui.app_user_id
    from public.user_identities ui
    where ui.auth_user_id =
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
    limit 1
$$;

alter table public.app_users enable row level security;
alter table public.user_identities enable row level security;
alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.teams enable row level security;
alter table public.team_members enable row level security;
alter table public.projects enable row level security;
alter table public.project_members enable row level security;
alter table public.invitations enable row level security;
alter table public.project_tags enable row level security;
alter table public.audit_log enable row level security;
alter table public.outbox_events enable row level security;

-- Application user rows: visible to (and creatable by) their owner only.
drop policy if exists app_users_self_select on public.app_users;
create policy app_users_self_select on public.app_users
    for select to authenticated
    using (id = public.current_app_user_id());
drop policy if exists app_users_self_insert on public.app_users;
create policy app_users_self_insert on public.app_users
    for insert to authenticated
    with check (id = public.current_app_user_id());
drop policy if exists user_identities_self_select on public.user_identities;
create policy user_identities_self_select on public.user_identities
    for select to authenticated
    using (app_user_id = public.current_app_user_id());

-- Shared membership predicate for every tenant-owned table.
create or replace function public.is_organization_member(p_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.organization_members om
        where om.organization_id = p_organization_id
          and om.app_user_id = public.current_app_user_id()
    )
$$;

create or replace function public.is_organization_admin(p_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.organization_members om
        where om.organization_id = p_organization_id
          and om.app_user_id = public.current_app_user_id()
          and om.role in ('owner', 'admin')
    )
$$;

drop policy if exists organizations_member_select on public.organizations;
create policy organizations_member_select on public.organizations
    for select to authenticated
    using (public.is_organization_member(id));
drop policy if exists organizations_member_insert on public.organizations;
create policy organizations_member_insert on public.organizations
    for insert to authenticated
    with check (created_by = public.current_app_user_id());
drop policy if exists organizations_admin_update on public.organizations;
create policy organizations_admin_update on public.organizations
    for update to authenticated
    using (public.is_organization_admin(id))
    with check (public.is_organization_admin(id));
drop policy if exists organizations_owner_delete on public.organizations;
create policy organizations_owner_delete on public.organizations
    for delete to authenticated
    using (
        exists (
            select 1 from public.organization_members om
            where om.organization_id = id
              and om.app_user_id = public.current_app_user_id()
              and om.role = 'owner'
        )
    );

drop policy if exists organization_members_member_select on public.organization_members;
create policy organization_members_member_select on public.organization_members
    for select to authenticated
    using (public.is_organization_member(organization_id));
drop policy if exists organization_members_self_insert on public.organization_members;
create policy organization_members_self_insert on public.organization_members
    for insert to authenticated
    with check (
        app_user_id = public.current_app_user_id()
        or public.is_organization_admin(organization_id)
    );
drop policy if exists organization_members_admin_update on public.organization_members;
create policy organization_members_admin_update on public.organization_members
    for update to authenticated
    using (public.is_organization_admin(organization_id))
    with check (public.is_organization_admin(organization_id));
drop policy if exists organization_members_admin_delete on public.organization_members;
create policy organization_members_admin_delete on public.organization_members
    for delete to authenticated
    using (public.is_organization_admin(organization_id));

drop policy if exists teams_member_all on public.teams;
create policy teams_member_all on public.teams
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

drop policy if exists team_members_self_or_admin_insert on public.team_members;
create policy team_members_self_or_admin_insert on public.team_members
    for insert to authenticated
    with check (
        (app_user_id = public.current_app_user_id()
         and public.is_organization_member(
             (select t.organization_id from public.teams t where t.id = team_id)))
        or public.is_organization_admin(
            (select t.organization_id from public.teams t where t.id = team_id))
    );

drop policy if exists team_members_member_select on public.team_members;
create policy team_members_member_select on public.team_members
    for select to authenticated
    using (public.is_organization_member(
        (select t.organization_id from public.teams t where t.id = team_id)));
drop policy if exists team_members_admin_update on public.team_members;
create policy team_members_admin_update on public.team_members
    for update to authenticated
    using (public.is_organization_admin(
        (select t.organization_id from public.teams t where t.id = team_id)))
    with check (public.is_organization_admin(
        (select t.organization_id from public.teams t where t.id = team_id)));
drop policy if exists team_members_admin_delete on public.team_members;
create policy team_members_admin_delete on public.team_members
    for delete to authenticated
    using (public.is_organization_admin(
        (select t.organization_id from public.teams t where t.id = team_id)));

drop policy if exists projects_member_all on public.projects;
create policy projects_member_all on public.projects
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

drop policy if exists project_members_self_or_admin_insert on public.project_members;
create policy project_members_self_or_admin_insert on public.project_members
    for insert to authenticated
    with check (
        (app_user_id = public.current_app_user_id()
         and public.is_organization_member(
             (select p.organization_id from public.projects p where p.id = project_id)))
        or public.is_organization_admin(
            (select p.organization_id from public.projects p where p.id = project_id))
    );

drop policy if exists project_members_member_select on public.project_members;
create policy project_members_member_select on public.project_members
    for select to authenticated
    using (public.is_organization_member(
        (select p.organization_id from public.projects p where p.id = project_id)));
drop policy if exists project_members_admin_update on public.project_members;
create policy project_members_admin_update on public.project_members
    for update to authenticated
    using (public.is_organization_admin(
        (select p.organization_id from public.projects p where p.id = project_id)))
    with check (public.is_organization_admin(
        (select p.organization_id from public.projects p where p.id = project_id)));
drop policy if exists project_members_admin_delete on public.project_members;
create policy project_members_admin_delete on public.project_members
    for delete to authenticated
    using (public.is_organization_admin(
        (select p.organization_id from public.projects p where p.id = project_id)));

drop policy if exists invitations_member_all on public.invitations;
create policy invitations_member_all on public.invitations
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

drop policy if exists project_tags_member_all on public.project_tags;
create policy project_tags_member_all on public.project_tags
    for all to authenticated
    using (public.is_organization_member(organization_id))
    with check (public.is_organization_member(organization_id));

-- Audit is write-only from the API roles: members may read their org's
-- trail, nobody inserts or mutates it outside the backend.
drop policy if exists audit_log_member_select on public.audit_log;
create policy audit_log_member_select on public.audit_log
    for select to authenticated
    using (organization_id is null or public.is_organization_member(organization_id));

-- The outbox is backend-only: RLS enabled with no policies denies every
-- API-role query, including the service-role-impersonating authenticated
-- role.
