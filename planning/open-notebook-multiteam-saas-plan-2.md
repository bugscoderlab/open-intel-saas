# Open Notebook Multi-Team SaaS — Consolidated Architecture and Delivery Plan

**Prepared:** 12 September 2026  
**Purpose:** Consolidate the decisions and recommendations from the planning discussion into one implementation reference.

---

## 1. Executive summary

The proposed product is a multi-organization, multi-team SaaS built as a maintained fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook). Open Notebook supplies the research foundation—source ingestion, document processing, notes, semantic and text search, contextual chat, reusable transformations, multiple AI providers, and podcast generation. The new product adds:

- Supabase authentication and independent application users.
- Organizations, teams, projects, roles, and tenant isolation.
- A structured competitor-intelligence domain.
- Automated competitor discovery and data collection.
- Structured extraction of services, prices, reviews, promotions, and changes.
- Analytics dashboards and an analytics-aware chatbot.
- A reusable subscription platform that can serve this SaaS and future products.
- Strict module boundaries so one unavailable feature does not stop unrelated features.

The recommended initial architecture is a **modular monolith**, not many microservices. Next.js remains the frontend and FastAPI remains the backend. Supabase provides Auth, managed PostgreSQL, `pgvector`, and Object Storage. Feature modules are kept independent inside the application. The subscription platform is a separate deployable system because it must be reusable across different SaaS products.

The initial valuable product slice is:

> Register → create organization → invite a team → create a project → add competitors → attach sources → process and search the evidence → chat with the research.

Automated crawling, structured analytics, monitoring, and commercial subscription enforcement are layered on after that flow is secure and reliable.

---

## Starting repository: maintained GitHub fork

This product should explicitly begin as a maintained fork of:

- **Upstream repository:** [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook)
- **License:** MIT
- **Observed version during planning:** `1.14.0`
- **Verified baseline (2026-09-12 research):** `1.14.0` is the latest release (commit `30c7e2a`, released 21 Jul 2026). Pin this tag and commit. Findings: `docs/research/open-notebook-internals.md`.
- **Implementation baseline:** Pin the exact release tag and commit hash immediately before development begins.

The observed version is planning context, not a permanently safe baseline. Open Notebook may change before implementation starts, so record the actual tag and commit in the fork's root documentation:

```text
Open Notebook upstream baseline
- Repository: https://github.com/lfnovo/open-notebook
- Release/tag: <exact-release-tag>
- Commit: <full-commit-hash>
- Fork date: <YYYY-MM-DD>
```

### Fork setup

Create the fork under the organization that will own the SaaS, then configure two remotes:

```bash
git clone https://github.com/YOUR_ORGANIZATION/open-notebook.git
cd open-notebook

git remote rename origin fork
git remote add upstream https://github.com/lfnovo/open-notebook.git
git remote -v
```

Recommended meanings:

```text
upstream → Original lfnovo/open-notebook repository
fork     → Product team's maintained fork
```

Create a product branch from the pinned baseline:

```bash
git switch -c product/open-intel-v1
```

### Upstream integration workflow

Do not merge upstream changes directly into the production branch. Use a dedicated integration branch:

```bash
git fetch upstream
git switch upstream-integration
git merge upstream/main
```

Then:

1. Review the upstream release notes and migrations.
2. Resolve changes inside the integration branch.
3. Run research, authorization, tenant-isolation, ingestion, and chat tests.
4. Verify database adapters and Supabase migrations.
5. Merge the tested integration branch into the product branch.

As authentication and persistence diverge from upstream, routine upstream updates will become more expensive. Keep modified upstream behavior behind interfaces and adapters to reduce repeated conflicts.

### Code ownership boundaries

| Code category | Maintenance approach |
|---|---|
| Reusable Open Notebook functionality | Keep structurally close to upstream where practical |
| Modified Open Notebook persistence | Isolate behind repositories and adapters |
| Modified authentication | Isolate behind the application identity interface |
| Multi-team platform foundation | Product-owned modules |
| Competitor intelligence | Product-owned module |
| Analytics and intelligence chat | Product-owned modules |
| External collectors | Product-owned provider adapters |
| Subscription platform | Separate product-neutral repository |

### License handling

The MIT license generally permits modification, redistribution, and commercial use. Preserve the required Open Notebook license and copyright notice in the fork and in redistributed copies. Clearly identify substantial product-owned modifications in project documentation. Obtain legal review before commercial launch if the product incorporates other dependencies, content sources, or data providers with separate terms.

### Fork versus clean regeneration decision

**Decision:** Use the fork, but build a new modular SaaS shell around it. Do not regenerate the entire application from zero, and do not spread product-specific modifications throughout the upstream codebase.

Treat adapted Open Notebook functionality as the initial **Research module**:

```text
New SaaS application shell
├── Platform: users, organizations, teams, projects, permissions
├── Research: adapted Open Notebook functionality
├── Competitor intelligence: new product-owned module
├── Collection: new product-owned adapters and jobs
├── Analytics: new product-owned module
├── Intelligence chat: new product-owned coordinator
└── Subscription integration: client for separate billing platform
```

Reuse or adapt these Open Notebook capabilities:

- FastAPI API foundations.
- Source ingestion and document processing.
- Chunking and embedding generation.
- Text/vector research search.
- Notebook chat and Ask workflows.
- Notes and transformations.
- Model configuration and Esperanto provider abstraction.
- Selected LangChain/LangGraph workflows.
- Podcast functionality.
- Useful Next.js research components and interaction patterns.

Build these as separate product-owned modules:

- Application users and identity mapping.
- Organizations, teams, projects, roles, and permissions.
- Competitors, services, prices, reviews, and observations.
- Google Maps, website, and social collection adapters.
- Structured analytics, charts, and analytical functions.
- Capability-aware intelligence-chat routing.
- Monitoring and change detection.
- Subscription-platform integration.

Replace these fork components gradually:

| Existing Open Notebook area | Target treatment |
|---|---|
| Shared password authentication | Replace with Supabase Auth adapter |
| Missing application-user model | Add `app_users` and `user_identities` |
| SurrealDB persistence | Replace behind PostgreSQL repositories |
| Local uploaded files | Replace behind an object-storage adapter |
| Single-tenant queries | Require organization/project scope |
| SurrealDB-tied command storage | Adapt or replace with modular jobs/outbox |
| Existing frontend auth state | Adapt for Supabase sessions |
| Research-only navigation | Place inside the wider SaaS shell |

### Vertical-slice migration strategy

Do not migrate every SurrealDB model before proving the product. Convert one complete flow at a time:

1. **Notebook slice:** Supabase login → organization/project → create and list notebook in PostgreSQL.
2. **Source slice:** Upload source → object storage → process → store metadata and chunks.
3. **Search slice:** Generate embedding → tenant-filtered `pgvector` retrieval → return results.
4. **Chat slice:** Question → authorized sources → retrieval → LLM → cited response.
5. **Notes and transformations:** Move remaining core research workflows.
6. **Optional capabilities:** Podcasts and less-used integrations migrate only when needed.

Introduce interfaces before replacing infrastructure:

```text
NotebookRepository  → Surreal implementation → PostgreSQL implementation
SourceRepository    → Surreal implementation → PostgreSQL implementation
SearchRepository    → Surreal implementation → pgvector implementation
ChatRepository      → Surreal implementation → PostgreSQL implementation
ObjectStorage       → Local implementation   → Supabase Storage implementation
IdentityProvider    → Shared password         → Supabase Auth implementation
```

The application layer depends on the interface, allowing old and new infrastructure to coexist during migration. Remove a SurrealDB implementation only after its replacement passes functional, migration, and tenant-isolation tests.

### Selective upstream adoption

The product is a maintained fork, not a permanent mirror of upstream `main`. Evaluate upstream work by category:

| Upstream change | Recommended action |
|---|---|
| New AI provider | Usually port into the Research module |
| Improved document parser | Port or merge after ingestion tests |
| Chat/RAG improvement | Evaluate and selectively port |
| SurrealDB migration | Usually ignore after PostgreSQL replacement |
| Shared-password changes | Ignore after Supabase Auth migration |
| Research UI improvement | Port selectively into Research screens |
| Docker/deployment change | Evaluate against the product deployment model |
| Podcast improvement | Port only if the module is supported/enabled |

A clean rebuild should be reconsidered only if later discovery shows that very little Open Notebook functionality remains useful, its internals prevent reasonable module boundaries, or maintaining the fork consistently costs more than replacing the Research module. That is not the recommended starting assumption.

---

## 2. Product scope and terminology

### 2.1 Collaboration hierarchy

```text
Application user
└── Organization group / customer account
    ├── Organization A
    │   ├── Teams
    │   └── Projects
    │       └── Research notebooks
    └── Organization B
        ├── Teams
        └── Projects
            └── Research notebooks
```

- **Application user:** Stable user identity used by the product, independent of the authentication provider.
- **Organization group:** Product-side container linking one or more organizations to a billing customer.
- **Organization:** Tenant and data-isolation boundary, such as a company, brand, branch, or client.
- **Team:** Department or working group inside an organization.
- **Project:** Collaboration and permission boundary. A project belongs directly to an organization and may optionally belong to a team.
- **Notebook:** Research container inherited from Open Notebook.
- **Source:** File, URL, pasted text, audio, video, spreadsheet, review set, or collected web content.
- **Competitor:** Structured business entity linked to evidence sources.

One user can belong to several organizations and teams. Organizations may share one subscription without sharing private data.

### 2.2 Billing hierarchy

```text
Subscription platform customer
├── Product subscription: Research / Competitor Intelligence
│   └── Entitlements
└── Product subscription: Future SaaS
    └── Different entitlements
```

A subscription belongs to a customer in the reusable subscription platform. The product stores only the external customer/subscription link and an entitlement snapshot.

---

## 3. Current Open Notebook stack

At the time of review, Open Notebook identifies itself as version `1.14.0` and uses the following technologies.

| Layer | Current technology |
|---|---|
| Frontend | Next.js, React, TypeScript, App Router |
| UI | Tailwind CSS, Radix UI, CVA |
| Frontend server state | TanStack Query |
| Frontend local state | Zustand |
| HTTP client | Axios |
| Streaming | Server-Sent Events |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic |
| Main database | SurrealDB |
| AI orchestration | LangChain and LangGraph |
| AI-provider abstraction | Esperanto |
| Content processing | Content Core |
| Background jobs | Surreal Commands |
| Token counting | `tiktoken` |
| Podcasts | Podcast Creator |
| Python dependency management | `uv` |

Verified against upstream v1.14.0 (commit `30c7e2a`, 2026-09-12): the table above holds; actual versions are newer — Next.js 16, React 19, Tailwind 4, Python `<3.13`, Content Core 2.x, Esperanto 2.25. Code layout: two Python packages — `api/` (HTTP layer only, 22 routers) and `open_notebook/` (domain models, database access, graphs, AI). All database access funnels through `open_notebook/database/repository.py`, so the migration seam is that one file, not per-model. Full findings: `docs/research/open-notebook-internals.md`.

Current service ports in local development are normally:

| Service | Port |
|---|---:|
| Next.js | 3000 |
| FastAPI | 5055 |
| SurrealDB | 8000 |

### 3.1 Current frontend model

The existing frontend follows a layered structure:

```text
Pages → feature components → hooks → API modules → FastAPI
                              ↘ stores
```

The current notebook workspace is centered on a three-panel layout:

```text
Sources | Notes | Chat
```

Users select which sources are included as full content, summary, or excluded from AI context. Search and Ask operate across stored sources; transformations apply reusable prompts to individual sources.

### 3.2 Current limitations for SaaS use

The current project is effectively single-tenant and uses simple shared password protection rather than individual production-grade user accounts. It does not natively provide:

- Multiple users with isolated data.
- Organizations, teams, and project memberships.
- Role-based permissions.
- Tenant-aware vector isolation.
- Subscription and entitlement management.
- Structured competitor records.
- Automated competitor discovery.
- Exact SQL analytics and charts.

These must be added or migrated.

---

## 4. Local development without Docker

Running the application locally without Docker is possible.

### 4.1 Unmodified Open Notebook

For the current stack, run these as native processes:

```text
Terminal 1: Native SurrealDB
Terminal 2: FastAPI API
Terminal 3: Background worker
Terminal 4: Next.js frontend
```

Approximate commands:

```bash
uv sync

surreal start \
  --user root \
  --pass password \
  file:./data/open-notebook.db

uv run --env-file .env \
  uvicorn api.main:app --reload --port 5055

make worker-start

cd frontend
npm install
npm run dev
```

Correction from 2026-09-12 research: upstream documents starting SurrealDB via Docker (`surrealdb:v2`); the native `surreal start file:...` form above is not in upstream's docs. It likely works (SurrealDB ships a single binary), but per the decision below, prefer not to need it at all.

### 4.2 Proposed stack

The recommended development arrangement is:

```text
Local machine
├── Next.js
├── FastAPI
├── Python worker
└── Optional Ollama

Managed Supabase
├── Auth
├── PostgreSQL + pgvector
├── Object Storage
└── Optional Realtime
```

This requires no Docker for normal application development, although it requires internet access to Supabase.

**Decision (2026-09-12):** no Docker in local development. Managed Supabase (Auth, PostgreSQL + pgvector, Object Storage) is the data platform, and everything possible runs there. SurrealDB is never adopted as a product dependency; if it is ever needed to run upstream code during the transition, run it as a native binary only, as a temporary bridge, and retire it as soon as the first migration slices pass their tests.

Running the complete Supabase platform locally without Docker is impractical because Supabase is a collection of services, not a single executable. A completely offline, Docker-free environment would instead require native PostgreSQL with `pgvector` plus separately chosen authentication and object-storage implementations.

---

## 5. SurrealDB and the Supabase decision

### 5.1 What SurrealDB is

SurrealDB combines document, relational, graph, full-text, and vector database concepts. Open Notebook uses it for application records, relationships, chunks, embeddings, search, settings, and command records.

It can be viewed conceptually as providing some of the combined functionality of:

```text
PostgreSQL + pgvector + document/graph capabilities
```

### 5.2 Can Supabase replace it?

Yes, but this is a persistence-layer migration, not an environment-variable change. Supabase can provide:

| Requirement | Supabase capability |
|---|---|
| Authentication | Supabase Auth |
| Application data | PostgreSQL |
| Vector embeddings | `pgvector` |
| Keyword search | PostgreSQL full-text search |
| Files | Supabase Object Storage |
| Access policies | PostgreSQL Row Level Security |
| Live UI status | Supabase Realtime, where useful |

The following Open Notebook functionality can be retained:

- Source parsing and chunking.
- Embedding generation.
- LLM integrations through Esperanto.
- LangChain/LangGraph workflows where useful.
- Prompts and transformations.
- Chat orchestration.
- Podcast generation.
- Next.js UI components and frontend patterns.

The main replacements are:

- SurrealDB models and queries.
- SurrealDB migrations.
- Search/vector persistence.
- File handling.
- Authentication and authorization.
- Background command persistence where tied to SurrealDB.

### 5.3 Recommended migration boundary

Use SQLAlchemy 2, `asyncpg`, and Alembic behind repository interfaces. Do not scatter Supabase database client calls throughout FastAPI.

```python
class NotebookRepository(Protocol):
    async def create(self, notebook: NotebookCreate) -> Notebook: ...
    async def list_for_project(
        self,
        organization_id: UUID,
        project_id: UUID,
    ) -> list[Notebook]: ...
```

FastAPI connects to Supabase as managed PostgreSQL:

```env
DATABASE_URL=postgresql+asyncpg://...
```

A future migration to another PostgreSQL host then primarily changes connection and infrastructure configuration rather than business logic.

---

## 6. Supabase portability

Migration difficulty depends on how deeply Supabase-specific functionality is embedded.

| Component | Future migration difficulty |
|---|---:|
| PostgreSQL tables/data | Low |
| Standard indexes and constraints | Low |
| `pgvector` embeddings | Low–medium |
| PostgreSQL functions | Low–medium |
| RLS policies tied to Supabase identity | Medium |
| Object Storage | Medium |
| Supabase Auth users and sessions | Medium–high |
| Realtime subscriptions | Medium–high |
| Edge Functions | Medium |
| Direct `supabase-js` data access everywhere | High |

### 6.1 Portability rules

1. Let FastAPI own business logic and authorization decisions.
2. Use SQLAlchemy for business-table access.
3. Keep migrations in Alembic or versioned SQL committed to the repository.
4. Put Supabase Auth behind an identity-provider interface.
5. Maintain stable application-user IDs separate from provider IDs.
6. Put storage behind an object-storage interface.
7. Store bucket/object keys, not permanent Supabase URLs.
8. Use standard PostgreSQL and `pgvector` features.
9. Keep processing in Python workers rather than Edge Functions.
10. Use Realtime only as an optional UI enhancement.

### 6.2 Possible future replacements

| Current | Future alternatives |
|---|---|
| Supabase PostgreSQL | Managed or self-hosted PostgreSQL |
| Supabase Auth | Keycloak, Authentik, Auth0, Clerk, WorkOS, Better Auth |
| Supabase Storage | S3, MinIO, Cloudflare R2 |
| Supabase Realtime | SSE, WebSocket service, database-event worker |
| `pgvector` | Keep `pgvector`, or export to Qdrant/another vector store |

---

## 7. Authentication and application users

Verified against upstream v1.14.0 (2026-09-12): access control is a single shared password — the client sends `OPEN_NOTEBOOK_PASSWORD` as a Bearer token; when unset, auth is disabled. There are no user accounts. (Caveat: upstream's `.env.example` and dev docs name `BASIC_AUTH_*`/`APP_PASSWORD`, variables the code never reads.) Upstream has formalized this posture as policy: PDR-001 (2026-07) is "single-user first," and the multi-tenancy request issue #869 is closed with no linked PR. Replacing this with real accounts is mandatory, not optional, and upstream is unlikely to collide with the fork on it.

Supabase Auth should continue to provide:

- Registration.
- Login and logout.
- Password hashing and recovery.
- Email verification.
- OAuth providers.
- MFA.
- Sessions and refresh tokens.
- JWT issuance.

The application should maintain its own user identity.

```text
Supabase auth.users
        ↓
user_identities
        ↓
app_users
        ├── organization memberships
        └── billing/customer memberships
```

### 7.1 Recommended tables

```sql
create table app_users (
    id uuid primary key default gen_random_uuid(),
    email text,
    display_name text,
    avatar_url text,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table user_identities (
    id uuid primary key default gen_random_uuid(),
    app_user_id uuid not null references app_users(id) on delete cascade,
    provider text not null,
    provider_subject text not null,
    email text,
    created_at timestamptz not null default now(),
    unique(provider, provider_subject)
);
```

For Supabase:

```text
provider = "supabase"
provider_subject = auth.users.id
```

All business tables reference `app_users.id`, not the provider-specific subject.

### 7.2 Provisioning flow

```text
User registers through Supabase Auth
→ Supabase creates auth.users
→ secure trigger or backend provisioning creates app_users
→ user_identities maps the Supabase subject to app_users.id
→ product assigns organization and team membership
```

### 7.3 FastAPI principal

FastAPI validates the JWT and converts provider-specific claims into a provider-neutral principal:

```python
@dataclass
class Principal:
    provider: str
    subject: str
    app_user_id: UUID
    email: str | None
```

```python
class IdentityProvider(Protocol):
    async def verify_token(self, token: str) -> Principal: ...
```

The browser must never submit `app_user_id` as proof of identity. FastAPI derives it from the verified JWT.

### 7.4 Future identity alternatives

- **Keycloak:** Best for enterprise, LDAP, SAML, OIDC, and complete self-hosting.
- **Authentik:** Friendlier self-hosted identity and SSO platform.
- **Clerk:** Fast managed implementation with organization features.
- **Auth0/WorkOS:** Strong enterprise identity and SSO capabilities.
- **Better Auth:** Useful if authentication should live inside a TypeScript application.

Keep organization/team membership in product tables rather than adopting a provider-specific organization model as the source of truth.

---

## 8. Multi-organization and team model

### 8.1 Core access tables

```text
organizations
organization_members
teams
team_members
projects
project_members
invitations
```

Suggested fixed roles for the first version:

| Scope | Roles |
|---|---|
| Organization | owner, admin, member |
| Team | manager, member |
| Project | editor, viewer |

Use internal permissions such as `project.read`, `source.create`, and `member.invite`, then map fixed roles to them. Do not scatter checks such as `role == "admin"` throughout route code.

### 8.2 Project ownership

A project belongs directly to an organization and optionally to a team:

```text
projects
- id
- organization_id       required
- owning_team_id         optional
- name
- visibility
- created_by
```

This allows private, team, and organization-wide projects and makes it possible to move a project between teams.

Every tenant-owned record should carry `organization_id`, even when it could be derived by joins. Important examples:

- Projects.
- Notebooks.
- Sources and source chunks.
- Notes.
- Chat sessions and messages.
- Processing jobs.
- Competitors and observations.
- Stored-file metadata.

This improves tenant filtering and reduces the risk of cross-organization vector retrieval.

### 8.3 Authorization flow

```text
Next.js sends Supabase JWT
→ FastAPI verifies JWT
→ FastAPI resolves app_user_id
→ endpoint resolves organization/project
→ centralized authorization service checks membership and permission
→ repository receives explicit tenant scope
→ database/vector query applies that scope
→ audit entry records important changes
```

Do not trust `organization_id` received from the browser. Validate it against the requested project and authenticated membership.

---

## 9. Tenant-aware storage and retrieval

### 9.1 Source chunks

```sql
create table source_chunks (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id),
    project_id uuid not null references projects(id),
    notebook_id uuid not null references notebooks(id),
    source_id uuid not null references sources(id),
    content text not null,
    embedding extensions.vector(1536),
    embedding_model text not null,
    embedding_dimensions integer not null,
    chunking_version text not null,
    created_at timestamptz not null default now()
);
```

Store the embedding model and chunking version so vectors can be audited, migrated, or regenerated.

### 9.2 Vector search

Every vector-search function must receive or derive the authorized organization/project scope. Authorization occurs before retrieval; the LLM never decides permission scope.

```text
organization_id
project_id
authorized notebook IDs
query embedding
similarity threshold
result limit
```

### 9.3 Object storage

Store files under stable, tenant-scoped object keys:

```text
organization-id/project-id/source-id/original-file.pdf
```

The database stores:

```text
provider
bucket
object_key
checksum
size_bytes
content_type
organization_id
created_at
```

Do not store permanent provider-specific URLs. FastAPI generates signed URLs only after verifying access.

---

## 10. Reusable subscription platform

Subscription management should be a separate, product-neutral system that can serve this project and future SaaS products.

### 10.1 Ownership boundary

The subscription platform owns:

- Customers.
- Products.
- Plans and prices.
- Subscriptions.
- Feature entitlements.
- Usage records.
- Checkout and billing portal sessions.
- Payment-provider webhooks.

The Open Notebook SaaS owns:

- Application users.
- Organization groups and organizations.
- Teams, projects, and notebooks.
- Access permissions.
- Product data and resource counts.

The billing owner should not automatically gain access to private organization data.

### 10.2 Generic subscription schema

```text
customers
customer_members
products
plans
prices
subscriptions
features
plan_entitlements
usage_records
webhook_events
```

Feature codes are product-scoped:

```text
research.max_organizations
research.max_members
research.max_projects
research.storage_bytes
research.monthly_ai_credits
research.audit_log

competitor.max_searches
competitor.max_locations
competitor.export_enabled
```

### 10.3 Plans covering one or more organizations

Use one universal billing model:

| Plan | Example organization limit | Example user limit |
|---|---:|---:|
| Free | 1 | 2 |
| Starter | 1 | 5 |
| Business | 3 | 30 |
| Agency | 10 | 100 |
| Enterprise | Configurable | Configurable |

A single-organization plan is simply `max_organizations = 1`. Higher plans allow more organizations. Organizations remain isolated even when they share the same billing customer.

Count distinct active users across covered organizations unless commercial requirements later demand per-organization seat counting.

### 10.4 Product integration

The product stores a link and cached snapshot, not subscription truth:

```text
billing_customer_id
subscription_id
subscription_status
entitlement_version
synchronized_at
```

The subscription platform offers a small API:

```http
POST /v1/customers
POST /v1/checkout-sessions
POST /v1/billing-portal-sessions
GET  /v1/subscriptions/{subscription_id}
GET  /v1/customers/{customer_id}/products/{product}/entitlements
POST /v1/entitlements/check
POST /v1/usage-events
```

The SaaS uses a service credential when calling this platform. This credential must never be exposed to browser code.

### 10.5 Entitlement caching and failure behavior

Do not call the billing service on every request. Cache an entitlement snapshot locally.

```text
Payment-provider webhook
→ subscription platform updates subscription
→ emits entitlement.updated
→ SaaS fetches new entitlement snapshot
→ SaaS stores local cache
```

If the billing platform is temporarily unavailable:

- Continue with the latest unexpired snapshot.
- Apply a controlled grace period.
- Preserve existing data.
- Do not immediately block all customer activity.
- Never delete data automatically because of billing state.

### 10.6 Initial subscription-platform stack

```text
FastAPI subscription API
Next.js administration/portal UI
PostgreSQL database
One payment-provider adapter
Simple background worker
Python and TypeScript SDKs
```

Keep provider integration behind a `PaymentProvider` interface. Use generic internal subscription IDs separate from external provider IDs.

---

## 11. Competitor intelligence capability

Open Notebook is a strong research/RAG foundation but is not, by itself, a complete competitor-intelligence system.

### 11.1 What can be reused immediately

- File and URL ingestion.
- Document extraction.
- Text and vector search.
- Chat using selected sources.
- Ask across sources.
- Reusable transformations.
- Notes and citations.
- Multiple AI providers.

### 11.2 What must be added

- Competitor discovery by industry and location.
- Google Maps collection.
- Full website crawling.
- Optional social-media collection.
- Structured service and price records.
- Historical observations and snapshots.
- Scheduled monitoring.
- Evidence approval workflow.
- Exact analytics and charts.
- Multi-tenant SaaS and subscriptions.

### 11.3 Collection pipeline

```text
Website / Google Maps / social URL
→ discovery and collection connectors
→ raw evidence
→ content processing
→ structured extraction
→ human verification
→ competitor database
→ research index
→ dashboards and chatbot
```

Potential connector types include Google Maps providers, Apify actors, Firecrawl, Jina, Crawl4AI, and permitted social-media collectors. Each is an adapter and can fail independently.

### 11.4 Structured competitor model

```text
competitors
locations
competitor_sources
services
competitor_services
price_observations
review_observations
promotions
competitor_snapshots
```

Important rule: store observations rather than overwriting facts.

```text
Full grooming: RM80 observed in July
Full grooming: RM88 observed in September
```

Each extracted fact should retain:

- Source reference.
- Evidence text/location.
- Observation date.
- Confidence score.
- Extraction version.
- Approval state.

This supports price history, change detection, audits, and corrections.

---

## 12. Analytics chatbot

The intelligence chatbot combines separate tools rather than sending all data to the LLM.

```text
User question
→ question/tool router
├── Research/RAG tool
├── Competitor lookup tool
├── Approved analytics tool
└── Fallback path
→ answer composer
→ answer with structured results and source evidence
```

### 12.1 Routing examples

| Question | Route |
|---|---|
| What services does Competitor A promote? | RAG + structured lookup |
| Who has the lowest grooming price? | Analytics query |
| Why do customers dislike Competitor B? | RAG over reviews |
| Show average rating by location | Analytics + chart |
| Which competitor has the strongest premium position? | Analytics + RAG evidence |
| What changed this month? | Snapshot analytics + evidence |

### 12.2 Safe first implementation

Use approved analytics functions rather than unrestricted text-to-SQL:

```text
compare_competitor_prices
get_service_coverage
get_rating_summary
get_competitor_changes
get_market_position
```

Later text-to-SQL should be limited by:

- Read-only credentials.
- An allowlisted analytics schema.
- Server-inserted tenant filters.
- SQL validation.
- Query timeout and row limits.
- Audit logging.

### 12.3 Degraded behavior

If analytics is unavailable, the chatbot can answer from research evidence and clearly state that numeric analysis was unavailable. If embeddings are unavailable, it can fall back to keyword search. If the LLM is unavailable, structured dashboards and manual data remain accessible.

---

## 13. UI/UX direction

The design work produced a single interactive HTML prototype with a top-level layout switch.

### 13.1 Current Open Notebook layout

The current-layout view represents the existing research workflow:

- Left navigation for Notebooks, Search & Ask, Podcasts, Models, and Settings.
- Notebook header and tabs.
- Three-panel workspace: Sources, Notes, and Chat.
- Source context levels.
- Focused document research rather than business analytics.

### 13.2 Proposed SaaS layout

The proposed view adds:

- Organization switcher.
- Competitor-intelligence project workspace.
- Market summary metrics.
- Competitor comparison matrix.
- Pricing trends.
- New intelligence/change signals.
- Competitor directory and filtering.
- Evidence/source library.
- Research versus Analytics chat modes.
- Team and plan/usage navigation.

The notebook remains one feature inside the wider project rather than becoming the whole product.

---

## 14. Modular architecture

Every feature must be independently available. The recommended first architecture is a modular monolith with one Next.js deployment, one FastAPI deployment, and one worker deployment, while maintaining enforceable module boundaries.

### 14.1 Application layers

#### Platform foundation

```text
platform/
├── configuration
├── database
├── authentication
├── app_users
├── organizations
├── authorization
├── feature_flags
├── capability_registry
├── events
├── jobs
├── storage
├── audit
└── observability
```

#### Research module

```text
research/
├── notebooks
├── sources
├── source_processing
├── chunks
├── embeddings
├── notes
├── transformations
├── search
├── chat
└── podcasts
```

#### Business feature modules

```text
features/
├── competitor_intelligence
├── analytics
├── intelligence_chat
├── market_monitoring
└── recommendations
```

#### Integrations

```text
integrations/
├── supabase_auth
├── supabase_storage
├── subscription_platform
├── apify
├── google_maps_provider
├── firecrawl
├── social_collectors
├── llm_providers
└── notifications
```

#### Frontend features

```text
frontend/src/features/
├── platform
├── research
├── competitors
├── analytics
├── intelligence-chat
├── monitoring
└── subscription
```

### 14.2 Backend module template

```text
modules/competitor_intelligence/
├── api/
├── application/
├── domain/
├── infrastructure/
├── migrations/
└── tests/
```

Dependency direction:

```text
API → Application → Domain
                    ↑
              Infrastructure implements interfaces
```

The domain layer must not depend on FastAPI, Supabase, SQLAlchemy models, a crawler provider, or payment-provider SDK.

### 14.3 Required versus optional dependencies

| Module | Required dependencies | Optional dependencies |
|---|---|---|
| Platform | PostgreSQL, authentication | Subscription service |
| Research | Platform, storage | Web extraction, podcasts, embeddings |
| Competitors | Platform | Collection, research |
| Collection | Platform | Individual external collectors |
| Analytics | Platform | Competitor structured data |
| Intelligence Chat | Platform, one LLM | Research, analytics, competitors |
| Monitoring | Platform, competitors | Collection, notifications |
| Recommendations | Platform, one LLM | Research, analytics |

A required dependency prevents a module from operating. An optional dependency only removes or degrades a capability.

### 14.4 Database ownership

One PostgreSQL database is acceptable initially, with separate schemas:

```text
platform.*
research.*
competitor.*
analytics.*
monitoring.*
integration.*
```

Rules:

1. A module owns its tables and writes only through its services.
2. Cross-module foreign keys are limited to stable platform identifiers.
3. Cross-module reads use services, contracts, or read models.
4. Analytics consumes read-only views or events rather than modifying source tables.
5. Every tenant-owned record includes `organization_id`.

### 14.5 Internal events

Modules communicate through events:

```text
SourceCollected
SourceProcessingCompleted
CompetitorCreated
CompetitorEvidenceUpdated
PriceObservationCreated
CompetitorChangeDetected
AnalyticsSnapshotReady
SubscriptionEntitlementsUpdated
```

Use a PostgreSQL outbox table and Python worker initially. Kafka is unnecessary for the initial product. A failed analytics consumer must not roll back a successfully collected source; it can retry its event later.

---

## 15. Capability, flag, permission, and entitlement model

These concepts must remain separate.

| Check | Question answered |
|---|---|
| Authorization | Is this user allowed to perform the action? |
| Entitlement | Has the customer purchased this feature/capacity? |
| Feature flag | Has this feature been released in this environment? |
| Capability health | Can this module operate right now? |
| Limit | Has the customer exceeded allowed usage? |

Final access is conceptually:

```python
can_use = (
    authorization.permitted
    and entitlement.allowed
    and feature_flag.enabled
    and capability.usable
    and not usage_limit.exceeded
)
```

### 15.1 Capability API

```http
GET /api/capabilities
```

Example states:

```text
available
degraded
unavailable
disabled
not_entitled
```

The frontend uses this endpoint to show, hide, disable, or annotate features. It must not guess availability.

### 15.2 Failure matrix

| Unavailable component | What continues to work |
|---|---|
| Apify | Manual competitors, notebooks, existing analytics |
| Google Maps provider | Website/manual input and existing data |
| Firecrawl | Files, pasted text, alternative extractors |
| Embedding provider | Keyword search and SQL analytics |
| LLM provider | CRUD, source viewing, dashboards, exports |
| Analytics module | Research chat and competitor directory |
| Research module | Competitor records and structured analytics |
| Subscription platform | Cached entitlements during grace period |
| Notification provider | Monitoring and in-app alerts |
| Podcast module | All research and intelligence functions |
| Social collector | Websites, Maps data, and manual evidence |
| Worker | Existing data remains readable; new tasks remain queued |

---

## 16. Phased implementation plan

### Phase 0 — Architecture preparation

Build:

- Fork the upstream GitHub repository under the product organization.
- Pin and document the exact upstream tag and commit baseline.
- Configure `fork` and `upstream` remotes plus an upstream-integration branch.
- Repository/module structure.
- Shared configuration.
- Module and capability registry.
- Feature flags.
- Database schema ownership conventions.
- Internal event/outbox mechanism.
- Standard errors and health checks.

Exit condition: modules can be independently enabled/disabled and the API still starts when an optional module is absent.

### Phase 1 — Multi-user platform foundation

Build:

- Supabase Auth integration.
- `app_users` and `user_identities`.
- Organizations and memberships.
- Teams and memberships.
- Projects and project memberships.
- Fixed roles and permissions.
- Tenant-aware request context.
- Audit foundation.

Exit condition: two organizations cannot access each other’s records, files, jobs, or vectors.

### Phase 2 — Research module migration

Migrate:

- Notebooks.
- Sources and processing.
- Notes.
- Chunks and embeddings.
- Text/vector search.
- Chat sessions.
- Transformations.
- Optional podcasts.

Exit condition: secure multi-organization Open Notebook functionality operates on Supabase/PostgreSQL.

### Phase 3 — Manual competitor directory

Build:

- Competitors and locations.
- Services and price observations.
- Evidence links.
- Manual create/edit/review flow.
- Connection between a competitor and research sources/notebooks.

Exit condition: users can maintain competitor profiles and attach evidence without any external crawler.

### Phase 4 — Collection integrations

Build:

- Website collection adapter.
- Google Maps discovery adapter.
- Optional social collection adapters.
- Scheduled jobs.
- Deduplication and content hashing.
- Retry and checkpoint handling.

Exit condition: one failed connector does not stop other collection work or remove the last successful snapshot.

### Phase 5 — Structured extraction

Build:

- Service, price, promotion, and positioning extraction.
- Review-topic extraction.
- Confidence scores.
- Evidence references.
- Human approval queue.
- Observation and extraction versioning.

Exit condition: raw evidence can become an approved, auditable structured observation.

### Phase 6 — Analytics

Build:

- Metric definitions.
- Read-only analytical views.
- Competitor comparison.
- Price trends.
- Service coverage.
- Review topics.
- Location comparisons.
- Dashboard widgets and CSV export.

Exit condition: dashboards remain available from existing structured data even when collectors or LLMs are unavailable.

### Phase 7 — Intelligence chatbot

Build:

- Question/tool router.
- Research search tool.
- Competitor lookup tool.
- Approved analytics functions.
- Answer composer and citations.
- Capability-aware partial answers.

Exit condition: the chatbot uses only available tools and clearly reports unavailable analysis rather than failing the whole conversation.

### Phase 8 — Monitoring and alerts

Build:

- Scan schedules.
- Snapshot comparison.
- Change detection.
- Review queue.
- In-app notifications.
- Optional email/Slack integrations.

Exit condition: monitoring works even if notification delivery is temporarily unavailable.

### Phase 9 — Commercial subscription integration

Integrate:

- Product/customer registration.
- Checkout and billing portal.
- Plan entitlements.
- Organization, member, project, storage, and AI-credit limits.
- Entitlement snapshots and grace periods.
- Usage reporting.

Exit condition: commercial access is enforced without requiring a synchronous billing-service call for every product request.

### Release milestones

| Release | Phases | Product state |
|---|---|---|
| Alpha | 0–2 | Multi-organization Open Notebook |
| MVP | 3–5 | Competitor directory with evidence and extraction |
| Beta | 6–7 | Analytics dashboard and intelligence chatbot |
| Commercial | 8–9 | Monitoring, alerts, and subscription enforcement |
| Expansion | Later | More collectors, advanced analytics, new SaaS products |

---

## 17. Security and isolation tests

Minimum tests include:

- User A cannot list, retrieve, edit, or delete User B’s organization data.
- Guessing another notebook or source ID returns no protected data.
- Vector/text search never returns another organization’s chunks.
- Chat cannot cite unauthorized sources.
- A background job cannot process another tenant’s source.
- File download URLs are issued only after access checks.
- Removing a member immediately removes authorization.
- A viewer cannot mutate project data.
- Changing `organization_id` in a request does not change the authorized scope.
- Service-role operations always apply explicit organization/project filters.
- Billing-account membership alone does not grant access to organization data.
- Disabling one module does not prevent unrelated modules from starting.
- Failed consumers retry events without rolling back successful producers.

The Supabase service-role key bypasses RLS. It must remain backend-only, and code using it must apply explicit tenant filters. Prefer user JWT/RLS for appropriate user-scoped operations and reserve service-role access for tightly controlled administration and workers.

---

## 18. Initial scope versus postponed scope

### Build now

- Modular platform foundation.
- Supabase Auth with independent application users.
- Organizations, teams, projects, and fixed roles.
- PostgreSQL, `pgvector`, and object-storage abstractions.
- Migrated notebook/source/note/search/chat flow.
- Manual competitor directory.
- Evidence linkage.
- Basic capability states.

### Add after core validation

- Automated Maps/website collection.
- Structured extraction and approval.
- Analytics dashboards.
- Analytics-aware chatbot.
- Scheduled monitoring.
- Subscription enforcement.

### Postpone until demand exists

- Custom role editor.
- Enterprise SSO/LDAP.
- Fully autonomous agents.
- Unrestricted text-to-SQL.
- Multiple payment providers.
- Usage-based invoicing and complex proration.
- Reseller hierarchies.
- Real-time monitoring of every source.
- Predictive market-share claims.
- Large-scale social-media crawling.

---

## 19. Repository and deployment recommendation

### Product repository

```text
open-intel-saas/
├── frontend/
├── api/
├── modules/
│   ├── platform/
│   ├── research/
│   ├── competitor_intelligence/
│   ├── analytics/
│   ├── intelligence_chat/
│   └── monitoring/
├── integrations/
├── migrations/
├── tests/
└── docs/
```

### Subscription repository

```text
subscription-platform/
├── apps/
│   ├── api/
│   └── admin-web/
├── packages/
│   ├── python-sdk/
│   ├── typescript-sdk/
│   └── contracts/
├── migrations/
└── docs/
```

### Initial deployment units

```text
Product
├── Next.js frontend
├── FastAPI API
└── Python worker

Data platform
└── Supabase: Auth, PostgreSQL, pgvector, Storage

Commercial platform
├── Subscription FastAPI API
├── Billing/admin frontend
└── Subscription worker
```

Do not split each product module into a separate deployed service until scaling, security, or ownership demands it.

---

## 20. Definition of modular completion

A module is sufficiently independent when:

- It can be disabled through configuration.
- The API and unrelated modules still start.
- Its frontend entry reflects disabled, unavailable, or not-entitled state correctly.
- Its migrations and database tables have clear ownership.
- Its jobs are separately identifiable and retryable.
- Its failure does not roll back unrelated jobs.
- Cross-module communication uses documented contracts or events.
- It does not directly mutate another module’s tables.
- It has a defined fallback or degraded behavior.
- It includes tenant-isolation tests.
- Runtime availability is separate from commercial entitlement.
- Removing one vendor adapter affects only that adapter’s capability.

---

## 21. Final recommended direction

Proceed with this architecture:

```text
Maintained Open Notebook fork
        ↓ adapted as Research module
New Next.js modular SaaS shell
        ↓ Supabase JWT
FastAPI modular backend
├── Platform foundation
├── Open Notebook research module
├── Competitor intelligence
├── Analytics
├── Capability-aware intelligence chat
└── Monitoring
        ↓
Supabase PostgreSQL + pgvector + Object Storage

Separate reusable subscription platform
        ↓
Products, plans, subscriptions, entitlements, and usage
```

The first implementation should prove a secure end-to-end vertical slice rather than building every module at once:

```text
Register
→ create organization
→ invite member
→ create project
→ create notebook
→ add competitor and evidence
→ process source
→ search/chat within authorized scope
```

After that slice passes cross-tenant security and failure-isolation tests, add automated collection, structured extraction, analytics, monitoring, and subscription enforcement in the phases described above.

---

## 22. References reviewed during planning

- [Open Notebook repository](https://github.com/lfnovo/open-notebook)
- [Open Notebook development setup](https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/development-setup.md)
- [Open Notebook API reference](https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/api-reference.md)
- [Open Notebook frontend architecture](https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/frontend.md)
- [Open Notebook Python dependencies](https://github.com/lfnovo/open-notebook/blob/main/pyproject.toml)
- [Open Notebook Chat, Ask, and Transformations](https://github.com/lfnovo/open-notebook/blob/main/docs/2-CORE-CONCEPTS/chat-vs-transformations.md)
- [Open Notebook advanced configuration](https://github.com/lfnovo/open-notebook/blob/main/docs/5-CONFIGURATION/advanced.md)
- [Open Notebook multi-tenancy feature discussion](https://github.com/lfnovo/open-notebook/issues/869)
- [Supabase vector columns](https://supabase.com/docs/guides/ai/vector-columns)
- [Supabase JWT documentation](https://supabase.com/docs/guides/auth/jwts)
- [Keycloak application security documentation](https://www.keycloak.org/docs/25.0.6/securing_apps/index.html)
- [Authentik OAuth/OIDC documentation](https://version-2026-8.goauthentik.io/add-secure-apps/providers/oauth2/)
- [Better Auth organization plugin](https://better-auth.com/docs/plugins/organization)
