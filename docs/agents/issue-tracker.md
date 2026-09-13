# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues in **`bugscoderlab/open-intel-saas`** — the product repo (`remote fork`). Upstream (`lfnovo/open-notebook`) is reference-only and never receives product issues. Use the `gh` CLI for all operations.

## Conventions

- **Always pass the repo explicitly**: this clone has two remotes (`fork`, `upstream`), so `gh`'s automatic inference is unreliable. Every command below takes `--repo bugscoderlab/open-intel-saas`.
- **Default branch is `product/open-intel-v1`** (not `main`): spec #9 and tickets #11–#20 landed there directly; feature branches integrate into it. The upstream-integration branch is separate.
- **Create an issue**: `gh issue create --repo bugscoderlab/open-intel-saas --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --repo bugscoderlab/open-intel-saas --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --repo bugscoderlab/open-intel-saas --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --repo bugscoderlab/open-intel-saas --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --repo bugscoderlab/open-intel-saas --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --repo bugscoderlab/open-intel-saas --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42 --repo bugscoderlab/open-intel-saas` and fall back to `gh issue view`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `bugscoderlab/open-intel-saas`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo bugscoderlab/open-intel-saas --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets. (Phase 0–1 already used this shape: map #1, decision tickets #3–#8, spec #9, build tickets #11–#20.)

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --repo bugscoderlab/open-intel-saas --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**. Add an edge with `gh api --method POST repos/bugscoderlab/open-intel-saas/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/bugscoderlab/open-intel-saas/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --repo bugscoderlab/open-intel-saas --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --repo bugscoderlab/open-intel-saas --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --repo bugscoderlab/open-intel-saas --body "<answer>"`, then `gh issue close <n>`, then append a context pointer to the map's Decisions-so-far.
