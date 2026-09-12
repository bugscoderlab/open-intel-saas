# PDR-003: Open Intel platform slice — tenancy, permissions, and the seams between layers

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: bugscoderlab/open-intel-saas#9 (spec), tickets #11–#20 (implementation), [ADR-006](ADR-006-migration-granularity.md) (migration policy for the new `migrations/` runner — same granularity rules apply), [code-standards.md](../code-standards.md)

## Context

The multi-organization SaaS slice adds a second database (managed Supabase Postgres) and a second web app (`shell/`) next to the upstream single-user stack, which stays untouched until Phase 2. Several structural decisions were made while coding tickets #11–#20 that the spec states as outcomes without stating the reasoning.

## Decision

**1. Tenancy is enforced twice, at different granularities, on purpose.**

The repository layer applies the authorization matrix (role × permission × most-specific-scope) on every query through the service connection (which bypasses RLS as `postgres`). Supabase RLS is the independent second net: it exists to stop *cross-tenant* leaks when some future path talks to Postgres with the user JWT (`authenticated` role) instead of the service connection. RLS policies are therefore **organization-granularity** (`is_organization_member(organization_id)`) — coarse on purpose. Fine-grained decisions (viewers don't mutate) are the matrix's job; making RLS repeat the matrix would duplicate the matrix in SQL and drift from it. §17 is satisfied by the combination; the matrix is the single source of truth for what a role may do.

**2. The permission matrix is data, and route code contains no role names.**

`modules/platform/domain/permissions.py` holds the role→permission map verbatim from spec §8. `AuthorizationService` resolves the most specific role a principal holds and answers yes/no per permission. Routers and services ask "may I `tag.create` here?" — they never compare role strings. UI gating mirrors the same derivation client-side.

**3. Mutations write an audit row and an outbox event in the same transaction.**

`audit_log` is the human/operator trail (actor, action, target, payload); `outbox_events` is the integration trail (domain events for Phase 2 consumers). Both are written inside the request's unit of work, before commit — never a second connection, never a fire-and-forget. Reads write neither.

**4. Email is a domain port with three injected providers.**

`ConsoleEmailProvider` (dev default: prints the accept URL to the API log), `ResendEmailProvider` (production), and `RecordingEmailProvider` (tests) all implement the port in `domain/email.py`. Which one `serve.py` wires is an environment decision, made once at the composition root.

**5. Layering is `api → application → domain`; infrastructure implements domain ports.**

Domain owns the ports (identity, email, unit-of-work protocols) and the errors. Infrastructure (SQLAlchemy repositories, Supabase JWT verification) implements them. The import-linter contracts in `pyproject.toml` enforce this: the layers contract permits `api → application → domain` only, and a second contract forbids every inner layer from importing infrastructure. `serve.py` and `scripts/seed_platform.py` are composition-root scripts *outside* `modules/` — they may wire anything, which is why the seed script does not live in `modules/platform/infrastructure/` (putting it there broke the layering contract by construction).

**6. Migrations are plain SQL files with a row-tracked runner.**

`migrations/0001…0005` run idempotently via `modules/platform.infrastructure.migrations` (or `make migrate`), tracked in `schema_migrations`. Editing an applied migration is forbidden; iterate by adding a new file (same policy as ADR-006). RLS/policy migrations are written idempotently (`drop policy if exists`) so re-application after an edit is safe during development.

**7. Accepting a team/project invitation lands the stranger in the organization.**

App-level invitations never touch `auth.users`. A team invite can reach an email with no org membership; on accept, the invitee is inserted as an org `member` (if not already one) *and* the team/project membership. Without the org row, role resolution short-circuits to None and RLS hides everything — a membership-shaped lockout.

## Alternatives considered

- **RLS at matrix granularity** — rejected: the matrix would live twice; SQL and Python would drift; §17 only asks for the cross-tenant net.
- **Service connection only, no RLS** — rejected: one compromised/misconfigured client away from a silent cross-tenant leak; the net must exist independently of the backend (spec §17, "independent").
- **Shared database with the upstream SurrealDB stack** — rejected: different consistency/tenancy model; Phase 2 owns that migration.
- **Next.js shell under `frontend/`** — deferred, not rejected: upstream `frontend/` stays as reference-to-port until Phase 2 removes it (see `shell/README.md`).

## Consequences

- Any new permission is a matrix edit + (if needed) one authorization-service lookup — no route changes.
- Bypassing the repository layer (raw SQL in a script) must re-apply the tenant filter itself, or connect as `authenticated` and let RLS do it.
- New infrastructure adapters implement domain ports and get wired in `serve.py`; nothing else changes.
