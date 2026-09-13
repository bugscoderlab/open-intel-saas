# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the domain glossary. It does not exist yet; `/domain-modeling` (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates it lazily. Until then, the de facto glossary is the spec issues (notably #9) plus `VISION.md`.
- **`docs/7-DEVELOPMENT/decisions/`** — decision records: `ADR-NNN-*` (upstream-inherited architecture decisions) and `PDR-NNN-*` (product decisions, e.g. PDR-003 for the platform slice tenancy/seams). Read the ones that touch the area you're about to work in.
- **`planning/`** — the multi-team SaaS plan-of-record (`plan-3.md`), the source of the phase roadmap and §-citations used across specs.
- **`AGENTS.md`** (root, `open_notebook/AGENTS.md`, `frontend/AGENTS.md`) — session rules and component conventions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront.

## File structure

Single-context repo:

```
/
├── CONTEXT.md                          ← created lazily by /domain-modeling
├── VISION.md
├── docs/7-DEVELOPMENT/decisions/       ← ADR-NNN-*, PDR-NNN-*
├── planning/                           ← plan-of-record, phase roadmap
├── modules/                            ← product modules (platform, research, …)
├── shell/                              ← product Next.js app
└── frontend/                           ← upstream reference-to-port (Phase 2+)
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md` (once it exists) or in spec #9: **Application user** (not "auth user") for the product's own identity row, **Organization** for the tenant, **Project tag** as two words. Don't drift to synonyms the project avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR/PDR conflicts

If your output contradicts an existing decision record, surface it explicitly rather than silently overriding:

> _Contradicts PDR-003 (RLS stays org-granularity), but worth reopening because…_
