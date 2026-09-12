# Open Intel shell

The product's Next.js frontend (App Router, strict TypeScript, Tailwind).
Hosts the Phase 0–1 platform screens (tickets #19/#20): auth (email +
OAuth through Supabase Auth), organization creation/switching, members,
invitations (invite form + emailed accept page), teams, projects, and
project tags. Role-derived UI mirrors the backend permission matrix:
controls a role is not entitled to are not rendered (org admin/owner →
everything, project editor / team manager → edit, viewer → read-only).

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

## Configuration

Copy `.env.example` to `.env.local`:

- `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the
  managed project's publishable (anon) key; safe for the browser.
- `NEXT_PUBLIC_API_URL` — the FastAPI platform backend
  (default `http://localhost:5055`, see `serve.py`; CORS is wide-open in
  dev per the repo's dev-default posture).

Invitation accept links are built by the backend from
`INVITATION_BASE_URL` (default `http://localhost:3000`) and land on
`/invitations/accept?token=…` in this app.

## Routes

| Route | Purpose |
|---|---|
| `/login`, `/register` | Email + OAuth entry points (unauthenticated visitors only ever see these) |
| `/org` | Organization picker + creation |
| `/org/[orgId]` | Dashboard: members, invites, teams, projects |
| `/org/[orgId]/projects/[projectId]` | Project detail: tags CRUD, project members |
| `/invitations/accept?token=…` | Emailed invitation accept page |
| `/auth/callback` | Supabase OAuth code exchange |

## Feature boundaries

`src/features/*` folders may not import each other at all
(`eslint-plugin-boundaries`, configured in `eslint.config.mjs`) — plan §14.1
makes feature folders independent, and shared code must live outside
`src/features` (`src/components/ui`, `src/components/layout`,
`src/components/invitation`, `src/lib`) when the need actually arises.
