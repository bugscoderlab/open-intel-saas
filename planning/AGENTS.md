# AGENTS.md

## What this directory is

Planning workspace for **Open Intel** — a multi-organization competitor-intelligence SaaS that began as a maintained fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook) (MIT, observed v1.14.0). This directory was folded into the product repository (`bugscoderlab/open-intel-saas`, branch `product/open-intel-v1`) so planning and code live in one repo; `bugscoderlab/opennotebook` remains as the **issue tracker only**.

- `open-notebook-multiteam-saas-plan-2.md` — the source of truth for architecture and delivery: modular monolith, Next.js frontend, FastAPI backend, Supabase (Auth, Postgres, pgvector, storage). Do not contradict it.
- `competitor-intelligence-workspace.html` — static UI prototype of the competitor-intelligence workspace. Single self-contained file: all CSS/JS inline, no build step, no external dependencies.

There is **no code, package manager, build, or test tooling yet**. Don't invent setup commands.

## Testing (required, not optional)

Always do unit testing and smoke testing:

- Any code added to this repo must ship with unit tests for new logic, run and passing before you report done.
- Smoke test after every change, even "docs-only" ones that touch the prototype:
  - Open `competitor-intelligence-workspace.html` in a browser and confirm it loads with no console errors.
  - Click through the main flows: sidebar nav items switch views (`data-view` buttons), "Add competitor" / toasts fire, mobile menu toggles. All interactions are stubbed inline handlers — none should be wired to a backend.
- There is no test runner configured. If you add code that needs one, set up the minimal runner in-repo and document the exact command here.

## Conventions

- Keep the HTML prototype self-contained: inline CSS/JS only, no frameworks, no external assets. It is a mockup for reference — do not convert it to a framework without being asked.
- The plan doc prescribes the future fork workflow: pin the upstream release tag + commit hash in fork docs, and merge upstream changes only via a dedicated integration branch (never directly into the product branch). Follow it when code work starts.

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues in [bugscoderlab/opennotebook](https://github.com/bugscoderlab/opennotebook) (via `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
