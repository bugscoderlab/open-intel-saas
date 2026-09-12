# Research: Invitation delivery mechanism (wayfinder ticket #6)

**Question:** Open Intel (multi-organization SaaS on Supabase) needs organization/team/project-scoped invitations. How should invitation emails actually be delivered and the flow structured?

**Constraints:** business logic in FastAPI/Python workers (plan §6.1 — no Edge Functions for core logic); invites target both existing users and strangers; free tier initially; plan already has an `invitations` table (plan §8.1).

All claims below are cited to official Supabase docs (supabase.com/docs) or the `supabase/auth` GitHub source (the Go service behind Supabase Auth). Research date: 2026-09-12.

---

## 1. Supabase Auth email delivery: how it works and its limits

### 1.1 Default (built-in) SMTP

- Every Supabase project gets a shared, built-in SMTP server so Auth emails (confirmations, magic links, invites, password resets) work out of the box. It is **not meant for production use**. (<https://supabase.com/docs/guides/auth/auth-smtp>)
- Unless you configure custom SMTP, **Supabase Auth refuses to deliver to addresses that are not members of the project's Supabase organization team** — all other addresses fail with *"Email address not authorized"*. (<https://supabase.com/docs/guides/auth/auth-smtp>)
- Shared-SMTP rate limit is **2 messages per hour** and "can change without notice". There is **no SLA** on delivery or uptime. (<https://supabase.com/docs/guides/auth/auth-smtp>)
- Independently, the Auth HTTP endpoints that send email (`/auth/v1/signup`, `/auth/v1/recover`, `/auth/v1/user`) are rate-limited to **2 emails per hour combined** (as of 3 Sep 2024), plus a 60-second per-address resend window; OTP endpoints default to 360 OTPs/hour. The 2-emails-per-hour email cap **can only be changed with custom SMTP**. (<https://supabase.com/docs/guides/platform/going-into-prod#auth-rate-limits>)

### 1.2 Custom SMTP

- Any SMTP-capable provider works (Resend, AWS SES, Postmark, SendGrid, ZeptoMail, Brevo). Configure in Dashboard → Authentication → Emails → SMTP Settings, or via Management API `PATCH /v1/projects/{ref}/config/auth`. Once saved, Auth sends to all addresses. (<https://supabase.com/docs/guides/auth/auth-smtp>)
- On first enabling custom SMTP, a **conservative default rate limit of 30 messages/hour** is imposed "to protect the reputation of your newly set up service"; you raise it on the Authentication → Rate Limits page. (<https://supabase.com/docs/guides/auth/auth-smtp>, <https://supabase.com/docs/guides/platform/going-into-prod#availability>)
- Recommended hardening from the same docs: set up DKIM/SPF/DMARC, use a custom auth domain, keep auth and marketing email on separate domains/from-addresses, disable link tracking in the SMTP provider (it can deform Supabase's single-use links), and beware corporate email scanners that prefetch links — Supabase email links are **single-use**, so a scanner can burn the link before the user clicks. (<https://supabase.com/docs/guides/auth/auth-smtp>, <https://supabase.com/docs/guides/platform/going-into-prod#email-link-validity>)
- Expiry: email links and OTPs sent by Supabase Auth have a **default 24-hour expiry**. (<https://supabase.com/docs/reference/python/auth-api>)

**Implication:** On the free tier, Supabase Auth email is usable only for the app's own team during development (pre-authorized recipients, 2 msgs/hour). Any real multi-tenant invite volume requires either custom SMTP (30/hour default, raisable) or sending invites from the application side with your own email provider.

## 2. `inviteUserByEmail` and `signUp`: behavior and metadata

### 2.1 `inviteUserByEmail`

- Admin-only (requires the service-role key); the endpoint lives at `POST /auth/v1/invite`. Source: `supabase/auth` `internal/api/invite.go` — `InviteParams{Email, Data}`, gated by `getAdminUser(ctx)`. (<https://github.com/supabase/auth/blob/master/internal/api/invite.go>)
- The `data` parameter is stored as **user metadata** (`raw_user_meta_data`), i.e. `user_metadata` — **not** `app_metadata`. It lands in the JWT's `user_metadata` claim, which the user can edit via `updateUser()`. There is no `app_metadata` parameter on the invite endpoint. (<https://github.com/supabase/auth/blob/master/internal/api/invite.go> — `params.Data` is passed straight to `SignupParams.Data`; <https://supabase.com/docs/guides/auth/managing-user-data> — sign-up `options.data` maps to `raw_user_meta_data` / user metadata; JWT claim list in <https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook>)
- Existing-user behavior from source: if the email belongs to a **confirmed** user, the call fails with *"User already registered"* (`ErrorCodeEmailExists`); if the user exists but is unconfirmed, it resends the invite. So `inviteUserByEmail` cannot invite existing (confirmed) users into a second org — a hard mismatch for multi-org SaaS. (<https://github.com/supabase/auth/blob/master/internal/api/invite.go>)
- The invite email is one of the auth emails subject to the §1 limits (shared SMTP pre-authorization + 2/hour; custom SMTP 30/hour default).

### 2.2 `signUp` with email confirmation

- `signUp` returns a user but **no session** while "Confirm email" is enabled; the user confirms via a link to `SITE_URL`/allow-listed redirect URLs. If called for an existing confirmed user, it returns an obfuscated user object (or `User already registered` when confirmations are off) rather than revealing/enrolling the account — the standard anti-enumeration behavior. (<https://supabase.com/docs/reference/python/auth-signup>)
- Like invite, the `options.data` parameter becomes `user_metadata`, not `app_metadata`. (<https://supabase.com/docs/guides/auth/managing-user-data>)

### 2.3 Where org/team/project scope can actually live

- `app_metadata` is only writable server-side (service role / admin API) and is the intended channel for authorization data; the JWT exposes both `app_metadata` and `user_metadata` as claims. (<https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook>)
- The documented way to put app-owned authorization data into tokens is the **Custom Access Token Hook**, which runs before token issuance and can add claims derived from your own tables (e.g. an `is_admin` flag in a `profiles` table). It can be implemented **as a Postgres function** (SQL example in the docs) — that variant is database logic, not an Edge Function, so it does not violate the plan's "no Edge Functions for core logic" rule. (<https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook>)
- Supabase's own guidance for user-related app data: keep it in `public` schema tables (e.g. `profiles`) with RLS, referencing `auth.users`, optionally synced via trigger — not crammed into auth metadata. (<https://supabase.com/docs/guides/auth/managing-user-data>)

## 3. Auth-level invites vs app-level invitation rows

| Property | Auth-level: `inviteUserByEmail` | App-level: `invitations` row + tokenized link |
|---|---|---|
| Delivery | Supabase Auth email (subject to §1 limits) | Any provider, sent from FastAPI worker (own API key, own quota) |
| Targets strangers | Yes (creates unconfirmed `auth.users` row) | Yes — auth user created only at accept time |
| Targets existing users | **No** — fails on confirmed users | Yes — accept step just attaches membership |
| Carries org/team/project scope | Only via `user_metadata` (`data`), which is user-editable and unsafe for authorization | First-class columns in the `invitations` table; token authorizes exactly one membership grant |
| Token semantics | 24h single-use link, but it's an *auth* credential (clicking logs you in/sets password) | App-controlled: expiry, single-use, revocable by deleting the row; never an auth credential by itself |
| Rate limits | 2 emails/hour shared SMTP; 30/hour default custom SMTP | Provider quota only (e.g. Resend/SES free tiers) |
| Multi-org per email | One `auth.users` row per email; invite flow assumes single-app enrollment | Unlimited invitations per email, one per org/team/project |

Additional security notes from the docs that apply to any link-based flow:

- **Single-use link pitfall:** corporate email scanners prefetch links and burn them; Supabase recommends routing the email link through a domain you control with a user-clicked "Sign in" button. The same pattern applies to our own tokenized accept links — land on a page that performs the accept POST on click, don't auto-consume tokens on GET. (<https://supabase.com/docs/guides/platform/going-into-prod#email-link-validity>)
- **Email-change pitfall:** `updateUser` email changes send confirmations (both old and new emails by default; "Secure email change" controls this). Invitations must therefore never key off "user confirmed this email" alone — membership grants must verify the *invitation token's* email matches the accepting user's verified email at accept time, otherwise an invite accepted after an email change could attach membership to the wrong account. (<https://supabase.com/docs/reference/python/auth-updateuser>)
- Keep email confirmations **enabled** (docs' security checklist), and consider CAPTCHA on signup to resist bot-driven signup abuse. (<https://supabase.com/docs/guides/platform/going-into-prod#security>, <https://supabase.com/docs/guides/auth/auth-smtp>)

## 4. Constraint check (plan §6.1 — no Edge Functions for core logic)

- App-level invitations keep 100% of business logic in FastAPI/Python workers + Postgres. ✔
- Auth-level invites would still require a FastAPI service-role caller, but the *decision of who gets invited and into what scope* would be smuggled through `user_metadata` and blocked by existing-user limits. ✘
- If JWT-based authorization is wanted later, the Custom Access Token Hook has a **Postgres-function** implementation, not an Edge Function. ✔ (<https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook>)

## 5. Recommended flow

**App-level invitation row + tokenized accept link; Supabase Auth signup/login only happens at accept time; send invite email from the FastAPI worker via a transactional email provider; configure custom SMTP (or the provider's SMTP) for Auth's own transactional emails when free-tier limits bite.**

1. **Create:** An org/team/project admin calls `POST /invitations` in FastAPI. The worker (service role) writes an `invitations` row — `{email, scope_type, scope_id, role, invited_by, expires_at}`, plus a `token_hash` of a crypto-random single-use token (hash stored, raw token only in the email). Idempotent on `(email, scope)`; re-invite rotates the token. No `auth.users` row is touched.
2. **Deliver:** The same worker sends the email through a transactional provider API (e.g. Resend/SES free tier) with a link `https://app.openintel.dev/invites/accept?t=<token>`. This bypasses the shared-SMTP 2/hour and pre-authorized-recipient restrictions entirely; provider quotas replace Auth email rate limits. (Limits reference: <https://supabase.com/docs/guides/auth/auth-smtp>, <https://supabase.com/docs/guides/platform/going-into-prod#auth-rate-limits>)
3. **Accept:** The link lands on a Next.js page that (on user click, per the scanner-safe pattern) calls `POST /invitations/accept` with the token. FastAPI validates: token exists, not expired (default e.g. 7 days, app-controlled), not used; then requires the browser to hold a Supabase session (existing user signs in; stranger completes `signUp` with email confirmation). It verifies the session's confirmed email **equals the invitation email** (guards the email-change pitfall), then marks the token consumed and inserts the membership row (`organization_members` / `team_members` / `project_members`) in one transaction. The invitation, not Auth metadata, is the source of truth for scope and role.
4. **Auth emails:** Supabase's own confirmation/reset emails stay on Supabase Auth. For development, the built-in SMTP suffices (team-only, 2/hour). For launch, configure **custom SMTP** in the Dashboard and raise the default 30 messages/hour Auth rate limit as needed; if per-hour caps still bite, Auth also supports a Send Email hook for provider-API sending. (<https://supabase.com/docs/guides/auth/auth-smtp>)
5. **Authorization (later):** Keep roles in app tables and check them in FastAPI (already the plan). If org membership must appear in JWTs for RLS, add a Custom Access Token Hook implemented as a Postgres function that reads the membership tables — no Edge Function required. (<https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook>)

**Explicitly rejected:** using `inviteUserByEmail` as the invitation mechanism — admin-only, rejects existing confirmed users, cannot carry trustworthy app scope (only user-editable `user_metadata`), and its delivery channel is capped at 2 emails/hour on shared SMTP (pre-authorized recipients only) / 30 per hour by default on custom SMTP. (<https://github.com/supabase/auth/blob/master/internal/api/invite.go>, <https://supabase.com/docs/guides/auth/auth-smtp>)

## Key limits a builder must know

- Shared (default) Supabase SMTP: **team-member recipients only, 2 messages/hour, no SLA**. (<https://supabase.com/docs/guides/auth/auth-smtp>)
- Auth email-sending endpoints: **2 emails/hour combined** (signup/recover/user); only changeable with custom SMTP. OTP: 360/hour. (<https://supabase.com/docs/guides/platform/going-into-prod#auth-rate-limits>)
- Newly configured custom SMTP: **30 messages/hour default** Auth cap until raised in Rate Limits settings. (<https://supabase.com/docs/guides/auth/auth-smtp>)
- Supabase email links: **single-use, 24h default expiry**; scanner prefetch can burn them — route through an intermediate click page. (<https://supabase.com/docs/guides/platform/going-into-prod#email-link-validity>, <https://supabase.com/docs/reference/python/auth-api>)
- `inviteUserByEmail`: service-role only; `data` → user metadata (not `app_metadata`); fails with "User already registered" for confirmed users. (<https://github.com/supabase/auth/blob/master/internal/api/invite.go>)
