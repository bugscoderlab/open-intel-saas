# Open Intel

Domain language for Open Intel, a multi-organization competitor-intelligence SaaS built as a maintained fork of Open Notebook. The full architecture source of truth is `open-notebook-multiteam-saas-plan-2.md`; this file is the glossary only.

## Language

### Platform

**Application user**:
A stable user identity owned by the product, independent of the authentication provider. All business tables reference its ID, never the provider's subject.
_Avoid_: Auth user, Supabase user

**Customer**:
A billing entity owned by the separate subscription platform. Owns subscriptions, plans, and payments; holds no application data.
_Avoid_: Billing account (ambiguous with Organization group), subscriber

**Organization group**:
The product-side container that links one or more Organizations to a single Customer for billing. Organizations in one group never share data.
_Avoid_: Account, billing group

**Organization**:
The tenant and data-isolation boundary — a company, brand, branch, or client. Every tenant-owned record carries its ID.

**Team**:
A department or working group inside an Organization.

**Project**:
The collaboration and permission boundary. Belongs directly to an Organization and optionally to a Team.
_Avoid_: Workspace

**Role**:
A fixed, scope-scoped membership level (org: owner/admin/member; team: manager/member; project: editor/viewer) mapped to permissions through a central matrix. Route code never checks role names directly.
_Avoid_: Access level, tier

**Permission**:
An internal `resource.action` string (e.g. `project.read`, `member.invite`) granted via roles. The catalog grows per slice; Research-module permissions arrive with the Research map, not before.
_Avoid_: Scope, grant

**Project tag**:
The trivial tenant-owned entity of the Phase 0–1 slice: per-project CRUD whose job is to prove the tenant-scoping pattern (`organization_id` + `project_id` on every row). Named to avoid collision with the Research module's Notes.
_Avoid_: Note, memo

### Research

**Source**:
Anything ingested for study: file, URL, pasted text, audio, video, spreadsheet, review set, or collected web content.

**Notebook**:
The research container inherited from Open Notebook. Lives inside a Project.

### Competitor intelligence

**Market**:
UI term for a Project configured for competitor intelligence, with a location scope and competitor set. Not a separate entity.
_Avoid_: Market workspace as a distinct domain object

**Competitor**:
A structured business entity linked to evidence sources, with locations, services, and observations. Belongs to a Project; the same real-world business is a separate record per market (deliberate duplication — see Market).
_Avoid_: Business (too broad), account

**Change**:
A new approved observation that supersedes the current known value for the same (competitor, location, service or review topic). Emits `CompetitorChangeDetected` at approval time; identical re-observations are not changes. Undetected changes surface in the UI as Signals.
_Avoid_: Diff, update, delta

**Review queue**:
The worklist of pending observations, unmatched service suggestions, and other items awaiting a human decision. Approving an observation both moves it into analytics and fires a Change when it supersedes a known value.
_Avoid_: Approval inbox, moderation queue

**Snapshot**:
The raw point-in-time capture of a competitor's presence (e.g. a scrape result). Retained, never overwritten, so Observations can be re-derived after extraction-version changes.

**Observation**:
A single extracted, approvable fact about a competitor ("Full grooming: RM88, September"). Carries source reference, observation date, confidence score, extraction version, approval state, and optional location scope. Approval states are pending / approved / rejected; rejected observations are retained for audit and extraction tuning. Only approved observations feed analytics, dashboards, and chatbot numeric answers; pending ones surface as review work. Observations are stored, never overwritten.
_Avoid_: Fact, data point

**Location**:
A physical branch where a Competitor operates. Observations may be scoped to a location; market-level analytics aggregate across a competitor's locations.
_Avoid_: Branch (use only when emphasizing the physical site), outlet

**Service**:
A canonical offering in a Market's service catalog (e.g. "Full grooming"), defined once per Project so price comparisons are apples-to-apples. Extraction maps raw text to a Service with a confidence score; unmatched extractions land in the review queue as suggestions, never as facts.
_Avoid_: Offering, listing, SKU

**Evidence**:
A role a Source plays when linked to a Competitor or Observation, not a separate entity. The link carries an approval state and an excerpt location pointing at the exact text span inside the Source.
_Avoid_: Proof, citation record

**Signal**:
UI-only label for "something changed that needs review" — the presentation of unreviewed Observations and detected changes. Not a persisted core entity; the durable truth is Observation plus the `CompetitorChangeDetected` event.
_Avoid_: Alert, notification (those are delivery mechanisms)
