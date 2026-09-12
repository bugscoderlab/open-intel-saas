# Research: App-user provisioning trigger on signup

**Ticket:** bugscoderlab/opennotebook#7 · **Date:** 2026-09-12 · **Status:** Research only — no code changes

## Question

Open Intel keeps its own `app_users` + `user_identities` tables (plan §7: all business tables reference `app_users.id`, never the auth provider's subject). After a Supabase Auth signup (email **or** OAuth), something must create the `app_users` row and the `user_identities` mapping. Plan §7.2 says "secure trigger or backend provisioning" without picking one. This file picks the mechanism.

**Constraints (from the ticket):** no Docker; business logic lives in Python workers; no privilege-escalation paths; must handle OAuth logins as well as email signup; must not create duplicate `app_users` rows on re-login.

## Options compared

### Option A — Postgres trigger on `auth.users` (`handle_new_user` pattern)

The officially documented pattern: a `security definer` PL/pgSQL function `public.handle_new_user()` fires `AFTER INSERT ON auth.users` and inserts into your own table; Supabase's docs caution that "if the trigger fails, it could block signups, so test your code thoroughly". [1]

- **Coverage:** the trigger fires on *every* insert into `auth.users`, which is how all signup paths — email/password, OAuth, magic link/OTP, anonymous, SSO — create their user row. It is the only mechanism that sees **OAuth signups without any client or backend involvement**. [1][2]
- **Atomicity:** the trigger runs in the same database transaction as the auth insert. Either the auth user and the `app_users` row both exist, or neither does — no partial signup, no retry/reconciliation queue needed. (Contrast with HTTP hooks: Supabase gives Postgres hooks a 2-second budget and HTTP hooks a 5-second budget with 3 retries on 429/503 — asynchronous semantics that *can* fail after the auth user already exists.) [1][3]
- **Security:** the documented function is `security definer` with `set search_path = ''` — the empty search path is the key hardening step against search_path hijacking. Supabase's auth-hooks guidance (same engine, different attachment point) recommends against `security definer` in favor of explicit grants, and notes that functions created via the dashboard run as the highly-privileged `postgres` role — so the function should be created via migration, own the *minimum* tables it writes, and have its `EXECUTE` grant revoked from `anon`/`authenticated`/`public`. [1][3]
- **Known caveat (OAuth identities):** in the OAuth `CreateAccount` path, supabase/auth calls `signupNewUser` (insert user row) **first**, then `createNewIdentity` (insert identity row), both in one transaction [4]. Therefore an `AFTER INSERT ON auth.users` trigger *cannot* see the new row in `auth.identities` at that moment. The fix is two triggers:
  1. `AFTER INSERT ON auth.users` → upsert `app_users` (`ON CONFLICT DO NOTHING`, keyed on the auth UUID or on normalized email).
  2. `AFTER INSERT ON auth.identities` → upsert `app_users` (again idempotent) **and** insert into `user_identities` (`ON CONFLICT DO NOTHING` on `(provider, provider_subject)`).
- **Duplicates on re-login:** logins update `auth.identities.last_sign_in_at` but insert nothing new, and triggers fire on insert only — so re-login cannot duplicate anything as long as both triggers are idempotent (`ON CONFLICT DO NOTHING`) rather than plain `INSERT`. [1][4]
- **Testability:** plain SQL functions — unit-testable with a real Postgres (no Docker needed if using an ephemeral/local `postgres` or `pg_virtualenv`-style harness); the function body is testable directly, unlike a webhook. Migration-versioned via `supabase migration new` as Supabase recommends for auth-adjacent functions. [3]

### Option B — Supabase Edge Function (HTTP hook / webhook on auth events)

- Edge Functions are **Deno/TypeScript-only**, and local development/testing of them **requires Docker** (`supabase start` / `supabase functions serve`), which the ticket explicitly excludes. (`--use-api` deploy fallback exists but doesn't remove the TypeScript-only constraint.) [5]
- The plan rule says keep processing in Python workers, not Edge Functions — an Edge Function would mean provisioning logic in TypeScript outside the Python codebase.
- Where an Edge Function *would* be justified: if provisioning needed to call external APIs (CRM, email enrichment) or do non-trivial work that shouldn't run in the signup transaction. That is not this case — the mapping insert is a 2-row write.
- Webhook-style invocation is also weaker operationally: HTTP hooks run with a 5-second budget, 3 retries on 429/503 only, and on permanent failure the auth user exists while `app_users` doesn't — a partial signup needing a reconciliation job. [3]

### Option C — FastAPI/backend provisioning (own signup endpoint + `auth.admin.create_user`, or post-signup client callback)

- supabase-py's Auth Admin API can `create_user()`, `get_user_by_id()`, `list_users()`, `delete_user()`, `invite_user_by_email()` etc., but it **requires the secret (service-role) key and "should be called on a trusted server. Never expose your secret key in the browser."** It also does not send confirmation emails itself (use `invite_user_by_email` or `generate_link` for that), and `create_user(email_confirm=True)` auto-confirms — meaning a backend-mediated email signup path either skips Supabase's standard confirm-email flow or reimplements it. [6]
- **The killer gap: OAuth signups never touch the backend.** `sign_in_with_oauth()` is a client-side redirect through the provider; the FastAPI service is not in the loop. Backend provisioning therefore needs a *post-login* "ensure profile exists" call anyway — at which point you have reimplemented the trigger in Python, with extra latency on every login, an extra authenticated endpoint (new attack surface), and a race window between first login and provisioning.
- Transactionality claim does not hold in practice: `auth.admin.create_user()` is an HTTP call to the Auth service; creating the `app_users` row afterwards is a second call. There is no distributed transaction — a crash between them leaves an orphaned auth user. The trigger (Option A) is the only genuinely transactional option.

## Constraint check (ticket requirements)

| Requirement | Option A (trigger) | Option B (Edge Fn) | Option C (backend) |
|---|---|---|---|
| No Docker | ✅ pure SQL | ❌ local dev needs Docker [5] | ✅ |
| Logic in Python workers | ⚠️ SQL, not Python (tiny; only provisioning boilerplate) | ❌ TypeScript | ✅ |
| No privilege escalation | ✅ with `set search_path=''`, migration-owned, grants revoked [1][3] | ✅ | ⚠️ service-role key on server [6] |
| Email + OAuth both covered | ✅ all paths insert into `auth.users` [1][4] | ✅ | ❌ OAuth misses backend |
| No duplicates on re-login | ✅ insert-only triggers + `ON CONFLICT DO NOTHING` | ✅ | ⚠️ needs idempotent upsert endpoint |

## Recommendation

**Option A: Postgres triggers on `auth.users` and `auth.identities`** — idempotent (`ON CONFLICT DO NOTHING`) inserts into `app_users` and `user_identities`, created via migration, `security definer` with `set search_path = ''`, `EXECUTE` revoked from `anon`/`authenticated`/`public`.

Rationale: it is the only mechanism that covers OAuth without any client cooperation, the only one that is transactional with the signup itself (no partial signup), requires no Docker, and keeps the service-role key out of the FastAPI surface. The cost — two small SQL functions — is provisioning boilerplate, not business logic; business rules on top of the provisioned rows still live in Python workers. Edge Functions are not justified (Deno/TypeScript, Docker for local dev, plan rule against them); backend admin provisioning remains necessary only for *admin-initiated* user creation (invites), not for self-serve signup.

### Failure modes a builder must handle

1. **Trigger failure blocks signup** (documented Supabase behavior [1]): keep both functions as small pure inserts; any non-essential work (welcome emails, enrichment) must go to a queue/worker, never the trigger.
2. **Partial signup — not possible via triggers** (same transaction), but real for the hybrid path: if the FastAPI backend later adds admin-created users (`auth.admin.create_user`), provisioning must still go through the same trigger functions so there is one code path.
3. **Duplicate `app_users` on re-login:** prevented because triggers fire on insert only and both use `ON CONFLICT DO NOTHING`; do not add "ensure profile" upserts in client-visible endpoints as a second code path.
4. **OAuth identity not visible in the `auth.users` trigger** [4]: `user_identities` rows must be written from the `auth.identities` trigger, not read from `auth.identities` inside the `auth.users` trigger.
5. **User deletes their auth account:** plan §7 forbids FKs to `auth.users`, so add an `AFTER DELETE ON auth.users` trigger (or `ON DELETE` handler) that deletes/anonymizes the `app_users` row. Note Supabase JWTs are stateless — a deleted user's access token remains valid until `exp` and refresh tokens are revoked at delete time; sensitive operations should check the session against `auth.sessions` or accept the short expiry window. [1]
6. **Email-confirmation-later:** with "Confirm email" enabled, the trigger fires at signup before confirmation — decide whether `app_users.status` starts as `pending` and is flipped by an `AFTER UPDATE OF email_confirmed_at ON auth.users` trigger, rather than gating row creation on confirmation. [1][6]
7. **Testability:** test the two functions by inserting fixtures into `auth.users`/`auth.identities` in a transaction and rolling back; add a pgTAP-style unit suite since repo tests must cover the new logic.

## Sources

1. Supabase Docs — "Managing User Data" (custom `handle_new_user` trigger pattern, `security definer set search_path = ''`, trigger failure blocks signup caution, `on delete cascade` guidance, JWT validity after delete): https://supabase.com/docs/guides/auth/managing-user-data
2. Supabase Docs — `auth.identities` / identities linked to a user (`get_user_identities`): https://supabase.com/docs/reference/python/auth-getuseridentities
3. Supabase Docs — "Auth Hooks" (Postgres hook grants to `supabase_auth_admin`, recommendation against `security definer`, 2s Postgres / 5s HTTP hook budgets, 3-retry rule for 429/503, version hooks via `supabase migration new`): https://supabase.com/docs/guides/auth/auth-hooks
4. supabase/auth source — OAuth `CreateAccount` inserts the user row (`signupNewUser`) before the identity row (`createNewIdentity`), same transaction: https://github.com/supabase/auth/blob/master/internal/api/external.go (function `createAccountFromExternalIdentity`)
5. Supabase Docs — "Edge Functions Quickstart" (TypeScript/Deno only; "Running and testing Supabase Edge Functions locally requires Docker"; `--use-api` deploy fallback): https://supabase.com/docs/guides/functions/quickstart
6. Supabase Docs — Python Auth Admin API (`create_user`, `email_confirm`, no confirmation email sent, "requires a secret key… should be called on a trusted server. Never expose your secret key in the browser"; `invite_user_by_email`; `delete_user` with `should_soft_delete`): https://supabase.com/docs/reference/python/auth-admin-createuser
