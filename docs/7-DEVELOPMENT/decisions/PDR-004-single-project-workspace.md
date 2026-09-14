# PDR-004: One workspace per project — the notebook is a feature inside it, not a parallel workspace

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: [plan §13.2](../../planning/open-notebook-multiteam-saas-plan-2.md) (UI/UX direction), [CONTEXT.md](../../planning/CONTEXT.md) (Project, Market, Evidence), `planning/competitor-intelligence-workspace.html` (prototype)

## Context

Plan §13 describes the design exploration as "a single interactive HTML prototype with a top-level layout switch": §13.1 the current Open Notebook layout (three-panel research workspace: Sources/Notes/Chat) and §13.2 the proposed SaaS layout (competitor-intelligence project workspace). The prototype implemented that switch as two top-level views. Read literally, this looks like two separate workspaces — and the current codebase reinforces the illusion: the `(dashboard)` frontend routes are inherited verbatim from upstream (`notebooks/`, `podcasts/`, `search/`, …) with no project-level route yet, while the backend `research` and `competitor_intelligence` modules are separate. CONTEXT.md already implies the answer (Project: "Avoid: Workspace"; Market: "not a separate entity"; Evidence: a role a Source plays) but never states it as a decision.

## Decision

**There is exactly one workspace: the Project.** A project configured for competitor intelligence is a "Market" in UI terms — same entity, same workspace, never a distinct domain object.

- The research notebook (Sources/Notes/Chat) is **one feature — one view — inside the project workspace**, alongside the competitor-intelligence views (market overview, competitors, review queue, evidence library, intelligence chat with Research/Analytics modes). It does not become the whole product, and it does not live in a second workspace.
- The prototype's layout switch is a **before/after comparison device only**; it must not survive as product navigation.
- The separate backend `research` / `competitor_intelligence` modules are **code organization within the modular monolith, not UX separation**. The domain link (Evidence = a role a Source plays when linked to a Competitor) only makes sense if both live in one workspace.

## Alternatives considered

- **Two top-level workspaces (research workspace + competitor-intelligence workspace)** — rejected: duplicates the source/evidence library, splits chat into two homes, and contradicts the Market definition in CONTEXT.md.
- **Notebook remains the whole product, CI bolted on** — rejected by plan §13.2; the product is competitor intelligence, research is the inherited foundation it stands on.

## Consequences

- New frontend work adds a project-level route whose navigation hosts both the notebook view and the CI views; no second workspace shell is built.
- CI views and the notebook share Sources natively (Evidence links to Sources, not to a parallel document store).
- New views are added to the project navigation, never as new workspaces; if a mockup ever shows two layouts again, label them "current"/"proposed", not as destinations.
