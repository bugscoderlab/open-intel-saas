# Open Intel shell

The product's Next.js frontend (App Router, strict TypeScript). Created in
ticket 10 as a placeholder home screen; auth, organization, and project
screens land in tickets 10 (UI) and 11.

**Why `shell/` and not `frontend/`?** Upstream's `frontend/` directory stays
in the tree untouched as reference-to-port until Phase 2 removes the leftover
upstream code (see `OPEN-INTEL.md`). At that point this app takes over the
`frontend/` slot of the plan §19 layout.

## Commands

```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # production build
npm run lint     # eslint, incl. the feature-boundary rules (plan §14.1)
```

## Feature boundaries

`src/features/*` folders may not import each other at all
(`eslint-plugin-boundaries`, configured in `eslint.config.mjs`) — plan §14.1
makes feature folders independent, and shared code must live outside
`src/features` (e.g. `src/lib`) when the need actually arises.
