# Module boundary enforcement mechanism — research findings

Wayfinder ticket #4 (bugscoderlab/opennotebook). Research only; no repo files modified except this file.
Investigated against primary sources (official docs, source repos). Constraint: everything must run in GitHub Actions on `ubuntu` runners, no Docker.

## 1. The boundary rules the mechanism must express (from the plan)

From `open-notebook-multiteam-saas-plan-2.md` §14:

- Backend layout: `platform/`, `research/`, `features/<module>/` (competitor_intelligence, analytics, intelligence_chat, market_monitoring, recommendations), `integrations/<adapter>/`.
- Each business module has the template `api/ → application/ → domain/` with `infrastructure/` implementing domain interfaces — explicitly "API → Application → Domain".
- "The domain layer must not depend on FastAPI, Supabase, SQLAlchemy models, a crawler provider, or payment-provider SDK."
- §14.3: required vs optional dependencies per module (a module must be disable-able without breaking others).
- §14.4: cross-module database access goes through services/contracts/events, not direct table mutation.
- §14.5: modules communicate via events (PostgreSQL outbox), not direct imports where a contract should be used.
- §20: "A module is sufficiently independent when: it can be disabled through configuration; the API and unrelated modules still start…" — i.e. feature modules must not import each other except via declared contracts.

So the mechanical enforcement must cover three things:

1. **Intra-module layering**: `api → application → domain` (one-directional), with `infrastructure` allowed to implement domain interfaces but not reverse the arrow.
2. **Domain purity**: `domain/` may not import `fastapi`, `supabase*`, `sqlalchemy`, crawler/payment SDKs.
3. **Inter-module independence/allowed-edges**: `platform` is the shared base; `research`, `features/*`, `integrations/*` are siblings that may not freely import each other (only through the declared contract/dependency edges of §14.3).
4. **Frontend**: `src/features/*` per plan §14.1 — feature folders that may not import each other's internals.

## 2. Python options compared

### 2.1 import-linter (recommended)

- What it is: a standalone PyPI tool ("Lint your Python architecture") that analyses the import graph and checks declarative **contracts**; configured in `.importlinter` INI or `[tool.importlinter]` in `pyproject.toml`; run via `lint-imports`; supports custom contract types. Source: https://import-linter.readthedocs.io/en/stable/index.html
- Contract types relevant here:
  - **`layers`** — higher layers may import lower layers, never the reverse; includes **indirect** imports; supports `containers` so one contract recurs across many packages, optional layers in parentheses, and multi-item layers (`a | b` = siblings independent within a layer). Source: https://import-linter.readthedocs.io/en/stable/contract_types/layers/
  - **`forbidden`** — prevent module set A importing module set B; supports **external packages** (`forbidden_modules` may include `django`, `requests`, etc., with `include_external_packages = True` in top-level config). Source: https://import-linter.readthedocs.io/en/stable/contract_types/forbidden/
  - **`independence`** — a set of modules may not depend on each other in either direction, even indirectly. Source: https://import-linter.readthedocs.io/en/stable/contract_types/independence/
  - Also `protected` (only allow-listed importers) and `acyclic_siblings`. Source: https://import-linter.readthedocs.io/en/stable/index.html
- Fit: pip-installable, single `lint-imports` command, plain text config in the repo, no build system, no Docker, trivially runnable in GitHub Actions. This is the tool the import-linter docs themselves position for exactly this job ("impose constraints on the imports between your Python modules").

### 2.2 Pantsbuild — too heavy for day one

- Pants is a full build system: every directory gets a `BUILD` file full of **targets** (`python_sources`, `python_tests`, …), dependency inference from imports, one BUILD file per directory recommended, `pants tailor` to generate them, `__defaults__`, parametrization, remote caching/execution, etc. Source: https://www.pantsbuild.org/stable/docs/using-pants/key-concepts/targets-and-build-files
- It can validate dependencies, but adopting Pants means adopting its whole target/BUILD-file model, its CI integration, and its mental overhead **before there is any code**. For a small team starting fresh with uv/pip + pytest, that is a large, premature commitment. Defer; revisit only if the monorepo grows to multiple deployable artifacts needing hermetic builds and remote caching.

### 2.3 Ruff — useful companion, not an architecture tool

- Ruff's **TID252** (`relative-imports`, from flake8-tidy-imports) bans relative imports via `lint.flake8-tidy-imports.ban-relative-imports`; its autofix is explicitly unsafe (ruff warns the rewritten absolute path can resolve differently at runtime). Source: https://docs.astral.sh/ruff/rules/relative-imports/
- Ruff's import rules operate on single import statements (style, sorting, banned modules per-file via per-file-ignores). It has **no layered-architecture or inter-module dependency-direction concept** — it cannot express "domain may not import fastapi while application may". For domain purity one would have to duplicate per-file `banned-module` style config per directory and still not get transitive/layer semantics. Use ruff for everything else; not for boundaries.

### 2.4 JS tools (dependency-cruiser) — wrong ecosystem for the backend

- dependency-cruiser validates JS/TS/CoffeeScript dependency graphs against rules in `.dependency-cruiser.js`; it is not a Python tool. Source: https://github.com/sverweij/dependency-cruiser — relevant only to the frontend section below.

## 3. Can import-linter express the plan's rules? Yes — concretely

With root packages `platform`, `research`, `features`, `integrations` (matching plan §14.1):

1. **Intra-module layering (API → Application → Domain)** — one `layers` contract with `containers`:
   ```ini
   [importlinter:contract:module-layers]
   type = layers
   containers =
       features.competitor_intelligence
       features.analytics
       features.intelligence_chat
       features.market_monitoring
       features.recommendations
   layers =
       api
       application
       domain
   ```
   Layers are listed high→low; the contract fails if a lower layer imports a higher one, **including indirectly** — this is exactly the plan's arrow. `containers` let one contract recur across every module without repetition, and `(infrastructure)`-style optional layers handle modules that don't yet have every subpackage. Sources: layers contract options (`layers`, `containers`, optional parenthesized layers, indirect-import semantics): https://import-linter.readthedocs.io/en/stable/contract_types/layers/
   - Caveat: import-linter layers check *dependency direction*, not "implements interfaces" semantics. The rule `infrastructure may import domain but domain must not import infrastructure` is satisfied by `infrastructure` sitting below `domain` — declare `layers = api / application / infrastructure / domain` only if infrastructure should never import application; otherwise use a separate `forbidden` contract (`source = *.domain`, `forbidden = *.infrastructure`, `*.api`, `*.application`).

2. **Domain purity (no FastAPI/Supabase/SQLAlchemy/crawler/payment SDK)** — `forbidden` contract with external packages:
   ```ini
   [importlinter]
   root_packages =
       platform
       research
       features
       integrations
   include_external_packages = True

   [importlinter:contract:domain-purity]
   type = forbidden
   source_modules =
       features.*.domain
       research.*.domain
   forbidden_modules =
       fastapi
       supabase
       sqlalchemy
       apify
       firecrawl
       stripe
   ```
   `forbidden_modules` "may include root level external packages… If external packages are included, the top level configuration must have `include_external_packages = True`". Source: https://import-linter.readthedocs.io/en/stable/contract_types/forbidden/

3. **Inter-module edges (§14.3 required/optional dependencies)** — `independence` for feature modules that must not touch each other, plus `forbidden` (or small `layers` groups) for the allowed edges:
   ```ini
   [importlinter:contract:features-independent]
   type = independence
   modules =
       features.competitor_intelligence
       features.analytics
       features.intelligence_chat
       features.market_monitoring
       features.recommendations
   ```
   Where a §14.3 dependency is required (e.g. monitoring → competitors), record it as an explicit `ignore_imports` entry so the exception is documented in the contract, or split into separate `forbidden` contracts per allowed edge. `ignore_imports` is a shared option of these contracts: https://import-linter.readthedocs.io/en/stable/contract_types/independence/
   - Note the plan's §14.5 event contract: cross-module *runtime* communication via the outbox is not an import, so import-linter cannot and need not police it — but it does prevent the shortcut of importing another module's internals directly, which is the failure mode §20 ("does not directly mutate another module's tables", "cross-module communication uses documented contracts or events") is aimed at.
   - Database-ownership rules (§14.4: no cross-schema foreign keys except stable platform IDs, analytics reads views) are **not** import-graph properties and need separate enforcement: a SQL lint/review rule (e.g. migration-time check that only `platform` migrations reference `organization_id` cross-schema) plus the tenant-isolation tests already mandated by §20. Flag as a gap, not something import-linter covers.

4. **Exhaustiveness** — `exhaustive = true` on the layers contract fails CI if anyone adds a new subpackage to a module without declaring which layer it belongs to. Source: https://import-linter.readthedocs.io/en/stable/contract_types/layers/

## 4. Next.js frontend boundary conventions

- Next.js official position: it is **"unopinionated about how you organize and colocate your project files"** and lists strategies (store project files outside `app`, top-level folders inside `app`, **split project files by feature or route**) plus mechanisms: private folders `_folder` (opted out of routing), route groups `(folder)`, and optional `src/`. Source: https://nextjs.org/docs/app/getting-started/project-structure
- So the plan's `frontend/src/features/{platform,research,competitors,analytics,intelligence-chat,monitoring,subscription}` is a conventional "split by feature" layout; Next.js gives naming conventions but **no import-boundary enforcement** — folders do not enforce anything by themselves.
- Enforcement options for TS/React:
  - **eslint-plugin-boundaries** — ESLint plugin; classify files into elements by glob (`features/*`), then policies (`boundaries/dependencies`) allowing/disallowing element-to-element imports, including external-module restrictions; gives in-editor feedback and runs in `next lint` / CI. ~1k stars, actively documented at jsboundaries.dev. Source: https://github.com/javierbrea/eslint-plugin-boundaries
  - **dependency-cruiser** — standalone JS/TS dependency-graph validator with `forbidden` rules (`from`/`to` path patterns), circular-dependency detection, config via `.dependency-cruiser.js`, eslint-like text output for builds. Heavier config, separate CI step, but stronger analysis and visualization. Source: https://github.com/sverweij/dependency-cruiser
  - Judgment for a small team: **eslint-plugin-boundaries** first. It rides on ESLint the project already runs (Next.js ships ESLint config support: `eslint.config.mjs` is a standard top-level file per the Next.js docs), so there is zero extra CI machinery — the boundary check is just another lint error. Adopt dependency-cruiser later if/when visualization, orphan detection, or stricter graph metrics become worth the config.

## 5. CI without Docker

- Backend: GitHub Actions `ubuntu-latest`, `pip install import-linter` (or `uv add --dev import-linter`), step `lint-imports`. Pure Python static analysis — no services, no Docker. The tool is a normal PyPI package with `lint-imports` entry point. Source: https://import-linter.readthedocs.io/en/stable/index.html
- Frontend: same job or a parallel job, `npm ci && npm run lint` where the ESLint config includes `eslint-plugin-boundaries`. No Docker.
- Recommended gate order in one workflow: ruff → lint-imports → pytest; eslint (with boundaries) → next build/typecheck.

## 6. Recommended minimal setup (day one)

**Backend:**
1. `import-linter` as the only boundary tool, config in `pyproject.toml` (`[tool.importlinter]`), four contract groups: per-module `layers` (api → application → domain, via `containers`), `forbidden` domain-purity contract (fastapi/supabase/sqlalchemy/crawler/payment SDKs), `independence` across `features/*` (with `ignore_imports` as the documented registry of §14.3 allowed edges), `exhaustive` layers where mature.
2. Keep ruff for style/quality including TID252 if absolute imports are desired, but not as a boundary mechanism.
3. CI: single ubuntu job step `lint-imports`.

**Frontend:**
4. `eslint-plugin-boundaries` with `features/*` elements and `default: "disallow"` cross-feature policies (shared `components`/`lib` explicitly allow-listed); runs inside the existing ESLint pass, so no extra CI step beyond `npm run lint`.

**What to defer:**
- **Pantsbuild** — full build-system adoption; only revisit for hermetic multi-artifact builds/remote caching at monorepo scale. Source: https://www.pantsbuild.org/stable/docs/using-pants/key-concepts/targets-and-build-files
- **dependency-cruiser** — adopt when graph visualization/orphan/cycle analysis is wanted beyond lint-time boundaries. Source: https://github.com/sverweij/dependency-cruiser
- **Database-ownership rules (§14.4)** — enforce via migration review checklist + tenant-isolation tests (§20), not import linting; consider a SQL-lint step later.
- **Custom import-linter contract types** — built-in layers/forbidden/independence suffice until a domain-specific rule appears.
