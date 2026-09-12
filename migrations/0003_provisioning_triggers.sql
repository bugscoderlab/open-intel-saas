-- 0003: Application user provisioning triggers (ticket #11, decision #7).
--
-- Two triggers, not one: the OAuth account path inserts auth.users before
-- auth.identities in one transaction, so the users trigger cannot see the
-- identity. Bodies stay minimal inserts only — a trigger failure blocks
-- the whole signup. All functions are security definer with an empty
-- search_path, and EXECUTE is revoked from every API-facing role.

-- auth.users insert → upsert the Application user (idempotent on email).
create or replace function public.provision_app_user_from_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.app_users (id, email, status, created_at, updated_at, last_sign_in_at)
    values (
        new.id,
        new.email,
        case when new.email_confirmed_at is null then 'pending' else 'active' end,
        coalesce(new.created_at, now()),
        coalesce(new.updated_at, now()),
        new.last_sign_in_at
    )
    on conflict (lower(email)) do nothing;
    return new;
end;
$$;

-- auth.identities insert → upsert the Application user (OAuth ordering)
-- and record the identity. provider_subject is the provider's own subject
-- (for the email provider, the email address itself).
create or replace function public.provision_app_user_from_auth_identity()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_email text;
    v_app_user_id uuid;
begin
    v_email := coalesce(
        new.identity_data ->> 'email',
        (select u.email from auth.users u where u.id = new.user_id)
    );
    if v_email is not null then
        insert into public.app_users (email, status, created_at, updated_at)
        values (v_email, 'pending', now(), now())
        on conflict (lower(email)) do nothing;
        select id into v_app_user_id
        from public.app_users
        where lower(email) = lower(v_email);
        if v_app_user_id is not null then
            insert into public.user_identities
                (app_user_id, auth_user_id, provider, provider_subject)
            values (v_app_user_id, new.user_id, new.provider, new.provider_id)
            on conflict (provider, provider_subject)
            -- Re-created auth accounts (delete + re-signup) refresh the link
            -- so the new JWT subject still resolves to the Application user.
            do update set auth_user_id = excluded.auth_user_id;
        end if;
    end if;
    return new;
end;
$$;

-- Email confirmation (or email change after confirmation) → activate and
-- keep the Application user's email in sync.
create or replace function public.sync_app_user_on_email_confirmation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.email_confirmed_at is not null then
        update public.app_users
        set email = new.email,
            status = 'active',
            updated_at = now()
        where lower(email) = lower(old.email);
    end if;
    return new;
end;
$$;

-- auth.users delete → remove the Application user row. No FK to
-- auth.users exists; email is the join key (provider subjects differ per
-- provider, email is the one stable claim across them).
create or replace function public.remove_app_user_on_auth_user_delete()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    delete from public.app_users
    where lower(email) = lower(old.email)
       or id in (
            select app_user_id
            from public.user_identities
            where auth_user_id = old.id
       );
    return old;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.provision_app_user_from_auth_user();

drop trigger if exists on_auth_identity_created on auth.identities;
create trigger on_auth_identity_created
    after insert on auth.identities
    for each row execute function public.provision_app_user_from_auth_identity();

drop trigger if exists on_auth_user_email_confirmed on auth.users;
create trigger on_auth_user_email_confirmed
    after update of email_confirmed_at on auth.users
    for each row execute function public.sync_app_user_on_email_confirmation();

drop trigger if exists on_auth_user_deleted on auth.users;
create trigger on_auth_user_deleted
    after delete on auth.users
    for each row execute function public.remove_app_user_on_auth_user_delete();

revoke execute on function public.provision_app_user_from_auth_user() from anon, authenticated, public;
revoke execute on function public.provision_app_user_from_auth_identity() from anon, authenticated, public;
revoke execute on function public.sync_app_user_on_email_confirmation() from anon, authenticated, public;
revoke execute on function public.remove_app_user_on_auth_user_delete() from anon, authenticated, public;
