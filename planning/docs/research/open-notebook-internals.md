# Open Notebook internals — research findings

**Subject:** `lfnovo/open-notebook` at release **v1.14.0** (tag commit `30c7e2a63e43b7f270fc2c638f0b6246934a53f4`)
**Method:** primary sources only — GitHub release/tag pages, `raw.githubusercontent.com` file fetches at tag `v1.14.0`, GitHub git-tree API, and issue pages. No blog write-ups were used.
**Observation date:** 2026-09-12. v1.14.0 is the **latest** release (released 21 Jul 2026, marked "Latest" on the releases page); there is no newer release to drift against. Note the repo moves fast — v1.11.0 → v1.14.0 all shipped within July 2026, so re-pin before code work starts.

---

## 1. Does release/tag v1.14.0 exist? What is the latest release?

**Confirmed. v1.14.0 exists and is the latest release.**

- Release "v1.14.0 — New Providers & Hardened Provider Connections" is tagged at commit `30c7e2a63e43b7f270fc2c638f0b6246934a53f4` and marked `Latest`. Released 21 Jul 2026.
  - https://github.com/lfnovo/open-notebook/releases/tag/v1.14.0
- Tags API lists v1.14.0 as the newest tag (then v1.13.0, v1.12.0, v1.11.0, v1.10.0…).
  - https://api.github.com/repos/lfnovo/open-notebook/tags
- `pyproject.toml` at the tag declares `version = "1.14.0"`.
  - `pyproject.toml` — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/pyproject.toml

**Version drift:** none beyond the tag. The plan's pin target is current.

---

## 2. The stack table

**Mostly confirmed, with version corrections and two clarifications.**

| Plan claim | Verdict | Evidence |
|---|---|---|
| Frontend: Next.js, React, TypeScript, App Router | **Confirmed** (versions newer than plan implies) | `frontend/package.json`: `next ^16.2.6`, `react ^19.2.3`, `typescript ^5`; App Router via `frontend/src/app/` with route groups `(auth)`, `(dashboard)`. — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/frontend/package.json |
| Tailwind CSS, Radix UI, CVA | **Confirmed** (Tailwind v4) | `tailwindcss ^4`, `@tailwindcss/postcss`, 15 `@radix-ui/react-*` packages, `class-variance-authority ^0.7.1`, plus shadcn/ui-style `src/components/ui/` primitives. — same package.json |
| TanStack Query | **Confirmed** | `@tanstack/react-query ^5.83.0`; `src/lib/api/query-client.ts`, `QueryProvider`. — same package.json |
| Zustand | **Confirmed** | `zustand ^5.0.6`; stores in `src/lib/stores/` (auth, navigation, notebook-columns, notebook-view, sidebar, theme). — same package.json |
| Axios | **Confirmed** | `axios ^1.18.1`; client in `src/lib/api/client.ts`. — same package.json |
| Server-Sent Events | **Confirmed** | `frontend/src/app/api/_sse-proxy.ts` exists; architecture doc: streaming via `StreamingResponse(media_type="text/event-stream")`; v1.11.0 release notes: "end-to-end SSE streaming through the Next.js proxy" (PR #770). — `docs/7-DEVELOPMENT/architecture.md` https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/7-DEVELOPMENT/architecture.md |
| Backend: Python 3.11+, FastAPI, Uvicorn, Pydantic | **Confirmed** (upper bound added) | `requires-python = ">=3.11,<3.13"`; `fastapi>=0.104.0`, `uvicorn>=0.24.0`, `pydantic>=2.9.2`. — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/pyproject.toml |
| Database: SurrealDB for records, relationships, chunks, embeddings, search, settings, command records | **Confirmed** | See §3. Tables `notebook`, `source`, `source_embedding` (chunks), `source_insight`, `note`, `reference`/`artifact` relation tables; BM25 full-text indexes + `fn::text_search`/`fn::vector_search`; settings singletons (`open_notebook:default_models`); `source.command` RecordID to surreal-commands job. — `open_notebook/database/migrations/1.surrealql` https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/open_notebook/database/migrations/1.surrealql ; `open_notebook/domain/notebook.py` https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/open_notebook/domain/notebook.py |
| AI: LangChain/LangGraph | **Confirmed** (pinned to 1.x) | `langchain>=1.3.9,<2`, `langgraph>=1.0.5,<2`, plus provider packages (openai, anthropic, ollama, google-genai, groq, mistralai); `langgraph-checkpoint-sqlite`. — pyproject.toml |
| Esperanto provider abstraction | **Confirmed** | `esperanto>=2.25.1,<3`; architecture doc: "Esperanto enabling seamless integration with 17 AI providers" (v1.9.0 release notes say 2.22 — plan-era docs were behind). — pyproject.toml; architecture.md |
| Content Core | **Confirmed** (now 2.x) | `content-core>=2.0.4,<3`; v1.13.0 release: "Content Core 2.0" rebuilt extraction, pdfplumber replaces PyMuPDF (license motivation), opt-in Docling/Crawl4AI. — pyproject.toml; https://github.com/lfnovo/open-notebook/releases/tag/v1.13.0 |
| tiktoken | **Confirmed** | `tiktoken>=0.12.0`. — pyproject.toml |
| Podcast Creator | **Confirmed** | `podcast-creator>=0.12.0,<1`; `api/podcast_service.py`, `commands/podcast_commands.py`. — pyproject.toml; repo tree |
| Background jobs: "Surreal Commands" | **Confirmed** | `surreal-commands>=1.3.1,<2`; worker entry `surreal-commands-worker --import-modules commands`. — pyproject.toml; `Makefile` https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/Makefile |
| Dependency management: uv | **Confirmed** | `uv.lock` at root, `[tool.uv]` section in pyproject, `uv sync` in dev docs. — pyproject.toml; `README.dev.md` |
| Dev ports: Next.js 3000, FastAPI 5055, SurrealDB 8000 | **Confirmed for dev** | `docs/7-DEVELOPMENT/development-setup.md` uses ports 8000/5055/3000 throughout; `run_api.py` defaults `API_PORT=5055`. Note: **Docker deployments publish the frontend on 8502** (architecture.md diagram). — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/7-DEVELOPMENT/development-setup.md ; `run_api.py` https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/run_api.py |

Surprises in this row set: the frontend is **Next.js 16 / React 19 / Tailwind 4** (the repo's own architecture doc still says "Next.js 15 with React 19" — the doc lags the code), and Python is capped at `<3.13`.

---

## 3. What SurrealDB actually stores and how models are organized

**Confirmed in substance. The plan's mental model ("api/models or similar") is wrong about *where* the models live — see §8.**

**Schema (from migration 1, the owning source for the base tables):**
https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/open_notebook/database/migrations/1.surrealql

- `source` — SCHEMAFULL; `asset` (flexible object: file path / URL), `title`, `topics`, `full_text`, `created`/`updated`.
- `source_embedding` — chunk records: `source` (record<source>), `order`, `content`, `embedding` (array<float>).
- `source_insight` — transformation outputs: `source`, `insight_type`, `content`, `embedding`.
- `note` — `title`, `summary`, `content`, `embedding`.
- `notebook` — `name`, `description`, `archived` (soft-delete), `created`/`updated`.
- Relation tables: `reference TYPE RELATION FROM source TO notebook`; `artifact TYPE RELATION FROM note TO notebook`.
- `podcast_config` SCHEMALESS.
- Search: custom analyzer + BM25 full-text indexes on source title/full_text, chunk content, insight content, note content/title; database functions `fn::text_search` and `fn::vector_search` (cosine similarity over `embedding` arrays — **plain float arrays computed in SurrealQL, not a dedicated vector index type**).
- Settings singleton: `open_notebook:default_models` record.
- A `DEFINE EVENT source_delete` cascades embedding/insight deletes.

Later migrations (1→23 at the tag; `open_notebook/database/migrations/`, registered explicitly in `AsyncMigrationManager`, tracked in `_sbl_migrations`) add: `chat_session`, `transformation`, `credential` (with flexible `config` object, migration 15), `provider_config`, content settings, and podcast tables (episode/speaker profiles). — repo tree at commit `30c7e2a`.

**Model organization:** Pydantic `ObjectModel` base class (`open_notebook/domain/base.py`) with `table_name` ClassVar, CRUD via a repository layer (`open_notebook/database/repository.py` — `repo_query/create/update/delete/relate/upsert`), plus `RecordModel` singletons for one-per-install settings. Subclasses live in `open_notebook/domain/`: `notebook.py` (Notebook, Source, Note, SourceEmbedding, SourceInsight, ChatSession), `credential.py`, `provider_config.py`, `content_settings.py`, `transformation.py`. SurrealQL-injection allowlisting was added in the repository layer (v1.11.0, PRs #1002/#1021).
- `open_notebook/domain/base.py` — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/open_notebook/domain/base.py
- `open_notebook/domain/notebook.py` — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/open_notebook/domain/notebook.py

**Command records:** `Source.command` is a `RecordID` linking to a surreal-commands job in SurrealDB; status read via `surreal_commands.get_command_status` (`open_notebook/domain/notebook.py`). So the plan's "command records in SurrealDB" holds — the queue is DB-resident via the external `surreal-commands` package (`lfnovo/surreal-commands`).

---

## 4. The authentication model

**Confirmed: single shared password, Bearer-style, global. No per-user accounts. Two caveats below.**

- `api/auth.py` — `PasswordAuthMiddleware`: reads `OPEN_NOTEBOOK_PASSWORD` (or `OPEN_NOTEBOOK_PASSWORD_FILE` for Docker secrets) via `get_secret_from_env`. **"Auth is fully disabled (no hardcoded default password) if OPEN_NOTEBOOK_PASSWORD is not set."** Checks `Authorization: Bearer {password}` with `secrets.compare_digest` (constant-time, added v1.11.0 PR #1003). Excludes `/`, `/health`, `/docs`, `/openapi.json`, `/redoc`; `api/main.py` additionally excludes `/api/auth/status` and `/api/config`.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/api/auth.py
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/api/main.py
- The frontend keeps a login page (`frontend/src/app/(auth)/login/page.tsx`, `LoginForm.tsx`, `stores/auth-store.ts`, `lib/auth-token.ts`) that stores the shared password client-side and sends it as the Bearer token — one password == one global identity.
- The architecture doc itself flags it: "Auth middleware is basic (password-only); upgrade to OAuth/JWT for production."
  - `docs/7-DEVELOPMENT/architecture.md`

Caveats worth flagging:
1. **Doc/code mismatch:** `.env.example` at v1.14.0 documents `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD` under "# Security", but the middleware only reads `OPEN_NOTEBOOK_PASSWORD`. The username var is dead; the example file is stale. (https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/.env.example vs api/auth.py)
2. The dev-setup doc shows `APP_PASSWORD=` in its `.env` sample — also not the variable the code reads. (development-setup.md) So **three different names appear in docs for the one real env var**.

---

## 5. Background jobs: what are "Surreal Commands"? How does the worker run?

**Confirmed — with an important architectural note: the queue implementation is explicitly a swappable implementation detail.**

- Jobs are submitted with `surreal_commands.submit_command("open_notebook", <command>, {...})` — fire-and-forget, returns a command id; status polled via `GET /api/commands/{id}`.
- The worker is a separate process: `make worker-start` → `uv run --env-file .env surreal-commands-worker --import-modules commands --max-tasks ${OPEN_NOTEBOOK_WORKER_MAX_TASKS:-5}` (concurrency configurable since v1.14.0, default 5).
  - `Makefile` — https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/Makefile
- Registered commands (`commands/__init__.py`): `embed_source`, `embed_note`, `embed_insight`, `rebuild_embeddings`, `process_source`, `generate_podcast`.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/commands/__init__.py
- Usage in domain code: `Source.vectorize()` submits `embed_source`; `Note.save()` auto-submits `embed_note`; `Source.add_insight()` submits `create_insight`; source processing runs through `process_source` (graph in `open_notebook/graphs/source.py` driven by content-core).
  - `open_notebook/domain/notebook.py`
- ADR-004 (Accepted, 2026-07): "Long-running operations run as background jobs on a dedicated worker process, never inline in the API request cycle… The *queue implementation* is deliberately an implementation detail behind this decision. Today it's surreal-commands… A move to Celery is under evaluation as part of the Platform v-next cluster (#381)." Also: "A worker process is **required** for anything async to actually run… forgetting it is a silent-queue failure mode."
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/7-DEVELOPMENT/decisions/ADR-004-background-workers.md

**Implication:** the plan's "adapt or replace Surreal Commands with a jobs/outbox module" matches upstream's own stated direction — upstream may itself swap the queue to Celery, which would either simplify the fork's job migration or create merge friction.

---

## 6. Three-panel workspace, source context levels, Chat vs Ask vs Transformations

**All confirmed. One terminology correction on context levels.**

- **Three-panel workspace:** `docs/3-USER-GUIDE/interface-overview.md` documents the layout: left **Sources**, middle **Notes**, right **Chat**, with per-source context indicators (🟢 Full Content / 🟡 Summary Only / ⛔ Not in Context), token counter, and mobile stacking. Code: `frontend/src/app/(dashboard)/notebooks/[id]/page.tsx` with `SourcesColumn.tsx`, `NotesColumn.tsx`, `ChatColumn.tsx`.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/3-USER-GUIDE/interface-overview.md
- **Context levels — corrected terminology:** the implementation's modes are `full` | `insights` | `off` (`frontend/src/lib/types/notebook-context.ts`; logic in `frontend/src/lib/utils/source-context.ts`). The UI labels are "Full Content", "Summary Only", "Not in Context" — where "Summary Only" actually means **source insights** (transformation outputs such as auto-generated summaries), not an arbitrary summary field. The "included" default resolves to insights when a source has them, else full. Bulk actions: include / insights-only / full / exclude (v1.10.0, issue #223). Notes are binary: included (full) or off.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/frontend/src/lib/utils/source-context.ts
- **Chat vs Ask vs Transformations:** `docs/2-CORE-CONCEPTS/chat-vs-transformations.md` confirms the plan's semantics exactly:
  - **Chat** — multi-turn, *manual* context selection (you choose sources + levels); backed by `open_notebook/graphs/chat.py`, message history persisted in SurrealDB (`langgraph-checkpoint-sqlite` SqliteSaver in `/data/sqlite-db/`).
  - **Ask** — one question → LLM-planned search strategy → vector + text search over all sources → synthesized single answer, streamed via SSE; non-conversational; `open_notebook/graphs/ask.py`, `POST /api/search/ask`.
  - **Transformations** — reusable Jinja-templated prompts applied **one source at a time** (batch processing explicitly "planned for a future release"); output saved as `source_insight` records and optionally notes; `open_notebook/graphs/transformation.py`.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/2-CORE-CONCEPTS/chat-vs-transformations.md

---

## 7. Dev setup: ports, commands, 4-terminal Docker-less setup

**Confirmed with one correction: the repo's documented SurrealDB start is Docker-based, not a native `surreal start` binary command.**

- The repo's own dev guide (`docs/7-DEVELOPMENT/development-setup.md`) prescribes:
  - `uv sync` → confirmed (also `pip install -e .`).
  - SurrealDB: **Option A** `docker run -d --name surrealdb -p 127.0.0.1:8000:8000 surrealdb/surrealdb:v2 start --user root --pass password memory` (or `file:/data/surreal.db` with a volume), **Option B** `make database` (docker compose), **Option C** `docker compose up -d surrealdb`. All three are Docker; the guide lists "SurrealDB — Via Docker or binary" only as a prerequisite. The plan's native `surreal start --user root --pass password file:./data/open-notebook.db` is **plausible but not the documented command** (different data path, and v2 is the documented server version).
  - API: `uv run --env-file .env uvicorn api.main:app --host 0.0.0.0 --port 5055` — confirmed (plan's `--reload` variant also works; `make api` instead runs `run_api.py`, which defaults `reload=true`, `host=127.0.0.1`).
  - Worker: `make worker-start` — confirmed verbatim.
  - Frontend: `cd frontend && npm install && npm run dev` — confirmed.
  - Four individual terminals (DB / API / worker / frontend) is exactly the "Recommended for Development" layout in the guide — confirmed. (`make start-all` also exists and starts all four, with SurrealDB via docker-compose.)
- Ports 8000/5055/3000 confirmed (see §2). Docker deployment differs: frontend published on **8502** (architecture.md), API on 5055.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/7-DEVELOPMENT/development-setup.md
  - `Makefile`, `run_api.py` (URLs in §2/§5)

---

## 8. Repo/module layout relevant to extracting a "Research module"

**The plan's implicit assumption of a single backend tree is wrong — there are two top-level Python packages. This is the biggest structural correction.**

Top level at v1.14.0 (commit `30c7e2a`, full tree via GitHub git-trees API):

```
api/                    ← FastAPI app (HTTP layer only)
  main.py               ← app assembly, middleware, router registration, startup migrations
  auth.py, middleware.py
  models.py             ← Pydantic request/response schemas (NOT DB models)
  command_service.py, credentials_service.py, podcast_service.py
  routers/              ← 22 routers: notebooks, sources, notes, chat, source_chat,
                          search, transformations, models, credentials, providers,
                          settings, embedding, embedding_rebuild, podcasts,
                          episode_profiles, speaker_profiles, insights, commands,
                          config, auth, capabilities, languages
commands/               ← worker command registrations (embed_*, process_source,
                          generate_podcast) imported via --import-modules commands
open_notebook/          ← the installable package ("open-notebook" on PyPI)
  domain/               ← DB models: base.py (ObjectModel/RecordModel), notebook.py,
                          credential.py, provider_config.py, content_settings.py,
                          transformation.py
  database/             ← repository.py (SurrealQL access), migrate.py,
                          async_migrate.py, migrations/1..23 .surrealql
  graphs/               ← LangGraph workflows: source.py, chat.py, ask.py,
                          transformation.py, prompt.py, source_chat.py, tools.py
  ai/                   ← models.py (ModelManager), provider_registry.py,
                          model_discovery.py, connection_tester.py, provision.py
  podcasts/, utils/, config.py, exceptions.py
frontend/src/
  app/                  ← App Router: (auth)/login, (dashboard)/notebooks/[id],
                          search, podcasts, settings, transformations, sources/[id],
                          advanced + api/ proxy routes (incl. _sse-proxy.ts)
  components/           ← notebooks/ (3 columns), sources/, settings/, podcasts/,
                          search/, layout/, ui/ (shadcn-style primitives), …
  lib/                  ← api/ (axios clients per resource), hooks/, stores/ (zustand),
                          locales/ (14 languages), types/, utils/
prompts/, tests/, examples/, scripts/, docs/ (0-START-HERE … 7-DEVELOPMENT)
```

Citations: repo tree API at `30c7e2a` (https://api.github.com/repos/lfnovo/open-notebook/git/trees/30c7e2a63e43b7f270fc2c638f0b6246934a53f4?recursive=1); `pyproject.toml` (`[tool.setuptools] package-dir = {"open_notebook" = "open_notebook"}`); `api/main.py`; `open_notebook/domain/base.py`; `docs/7-DEVELOPMENT/architecture.md`.

**Extraction note:** a "Research module" maps cleanly onto `open_notebook/domain/notebook.py` + `graphs/{source,chat,ask,transformation}.py` + `api/routers/{notebooks,sources,notes,chat,source_chat,search,transformations,insights}.py` + `frontend/src/app/(dashboard)/notebooks/**` + `frontend/src/components/{notebooks,sources,search}/**`. The split between `api/` (delivery) and `open_notebook/` (domain) is already the repository-interface seam the plan's "Surreal impl → PostgreSQL impl" strategy needs — but the seam is per-function (`repo_query`, `repo_create`… in `repository.py`), not per-model, so the plan's "Repository per aggregate" abstraction is a genuine refactoring, not a rename.

---

## 9. Multi-tenancy: any existing multi-user or organization support?

**Confirmed absent — and this is now an explicit, governed upstream position, not just an accident.**

- Issue **#869** "[Feature]: Native Multi-User Support and Workspace Isolation (Multi-Tenancy)" (opened 8 Jun 2026 by GabrielRibeiroBatista) describes the current state accurately: "the application operates on a single-tenant model (using basic authentication)… anyone with access to the instance shares the exact same documents, chats, and workspaces." The issue is currently **Closed** with no linked PRs — i.e., requested but not delivered (and not accepted into a roadmap).
  - https://github.com/lfnovo/open-notebook/issues/869
- **PDR-001 "Single-user first; new features must not preclude multi-user"** (Accepted, 2026-07) is the stronger finding: "Open Notebook remains a **single-user product for now**… new features must not gratuitously preclude multi-user." It points to issue **#712** as the multi-user umbrella and explicitly defers the "team vs. SaaS-style" decision. Concretely, upstream now reviews features against "does this preclude multi-user?" — data models that *could* carry an owner scope and avoiding global singletons are the stated preference.
  - https://raw.githubusercontent.com/lfnovo/open-notebook/v1.14.0/docs/7-DEVELOPMENT/decisions/PDR-001-single-user-first.md
- Code-level confirmation: no user/tenant/org/role tables or columns anywhere in migrations 1–23 or the domain package; the only auth artifact is the single-password middleware (§4); chat sessions relate to notebooks/sources, never to users.

**Implication:** the plan's "effectively single-tenant" assumption is safe for v1.14.0, and PDR-001 means upstream feature PRs will increasingly avoid hard single-tenant assumptions — good for the fork's longevity, but each upstream merge must still be re-checked against the fork's tenant-scoping.

---

## Implications for the migration plan

**Assumptions that hold (verified against v1.14.0 primary sources):**
1. The whole stack table (§2) — every named dependency is present at the tag; only version numbers were stale in the plan's favor (Next.js 16, React 19, Tailwind 4, Python `<3.13`, Content Core 2.x, Esperanto 2.25).
2. SurrealDB really is the single store for records, relations, chunks, embeddings, BM25 search, settings singletons, and command/job records (§3) — the plan's "replace behind PostgreSQL repositories" strategy targets the right thing. Note embeddings are plain `array<float>` scored with `vector::similarity::cosine` in SurrealQL functions — a pgvector port is conceptually straightforward but the `fn::text_search`/`fn::vector_search` union-and-rank logic must be re-implemented.
3. Auth really is one shared `OPEN_NOTEBOOK_PASSWORD` Bearer token, disabled when unset; no users, no tenancy (§4, §9).
4. Background jobs really are surreal-commands, a separate required worker process, fire-and-forget with polling (§5) — and upstream's own ADR-004 treats the queue as swappable, validating the plan's outbox/job replacement.
5. Chat (manual multi-turn context) / Ask (auto-searched one-shot) / Transformations (one-source templates → insights) semantics match the plan exactly (§6).
6. Ports 3000/5055/8000 and the four-terminal workflow match the repo's dev guide (§7).

**Assumptions that need correcting:**
1. **Model location:** not "api/models" — DB models live in `open_notebook/domain/` (Pydantic `ObjectModel` + `repository.py` function seam); `api/models.py` is only request/response schemas. The plan's module-extraction and repository-interface tickets should reference `open_notebook/domain` + `open_notebook/database/repository.py`.
2. **Context levels:** the implementation modes are `full` / `insights` / `off`; the UI's "Summary Only" means *source insights* (transformation outputs), not a generic summary. Any UI/data-model copy in the plan saying "summary" should say "insights".
3. **Auth env var:** the single real variable is `OPEN_NOTEBOOK_PASSWORD`; `.env.example` (`BASIC_AUTH_USERNAME/PASSWORD`) and the dev-setup doc (`APP_PASSWORD`) name variables the code does not read. The plan should not propagate either name.
4. **Dev DB start:** the documented SurrealDB start is Docker (`surrealdb/surrealdb:v2`, memory or `file:` volume); the plan's native `surreal start … file:./data/open-notebook.db` is a reasonable but undocumented variant.

**Surprises:**
1. **Issue #869 (multi-tenancy) is Closed, and PDR-001 formalizes "single-user first, don't preclude multi-user"** — the plan is building the multi-tenant fork into a gap upstream has explicitly chosen not to fill yet, under a governance rule that will keep upstream code relatively fork-friendly on this axis. (§9)
2. **The auth documentation is inconsistent in three places** (code vs `.env.example` vs dev-setup doc) — when the fork replaces auth, trust `api/auth.py` only.
3. **Upstream is evaluating a move from surreal-commands to Celery** (ADR-004, issue #381) — the fork's job-system decision could either ride upstream's or diverge; either way, track #381 during upstream merges.
4. The repo's own `docs/7-DEVELOPMENT/architecture.md` lags the code (says Next.js 15; package.json says 16) — verify version-sensitive claims against manifests, not docs, on every upstream merge. Repo velocity is high (4 minor releases in July 2026 alone); re-pin the fork base shortly before code work begins.
