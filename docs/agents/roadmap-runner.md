# Roadmap runner (`/auto-matt --phase`, `ralph.sh`)

Unattended phase-by-phase execution of a project's roadmap. The global command
lives in `~/.config/opencode/commands/auto-matt.md`; the supervisor is
`~/.config/opencode/ralph.sh` (symlinked as `ralph`). Everything here is the
per-repo contract those global tools read.

## Contract

A repo is roadmap-runnable when it has:

1. The Matt Pocock conventions from `/setup-matt-pocock-skills`
   (`docs/agents/issue-tracker.md`, `triage-labels.md`, `CONTEXT.md`).
2. A `.auto-matt/roadmap.yaml` (below). If it is missing, `--phase` in
   checkpoint mode auto-drafts one from a detected spec doc and shows it at
   the first checkpoint; `--afk` refuses to run until a human has seen it.

## `.auto-matt/roadmap.yaml`

```yaml
repo: owner/name          # tracker repo; default: infer from git remote
branch: auto/roadmap      # side branch for phase-mode commits
push: true                # push that branch after each commit; default false
gate: make ci-local       # shell command before EVERY commit; red = halt
approval: checkpoint      # checkpoint (default) | afk
phases:
  - id: 3
    name: Manual competitor directory
    spec: ["plan.md", "plan.md#L1286-L1297"]   # markdown, optional line anchors
    mode: auto              # auto | gated
```

- `mode: auto` — prep (grill → spec → tickets) and implement everything.
- `mode: gated` — hard-gate items (real credentials, irreversible migrations,
  external authority, security sign-off) are published as `ready-for-human`
  tickets per `triage-labels.md`; the loop continues. They stay open at
  `ROADMAP-COMPLETE`, which then means "all automatable work landed".

## Markers (the supervisor greps these)

| Marker | Meaning |
|---|---|
| `<promise>COMPLETE</promise>` | Frontier/roadmap done (`ralph.sh` exits 0) |
| `<promise>ROADMAP-COMPLETE</promise>` | All configured phases done |
| `<promise>CHECKPOINT #N</promise>` + `checkpoint-repo: owner/name` | Prep done for a phase; `ralph.sh` polls issue `#N` for a `GO` comment (resume) or `HALT` (stop, exit 2) |

No marker after an attempt = crash/stuck ticket; the supervisor retries
(`--max-attempts`) within the wall-clock budget (`--max-hours`, default 8).
A stuck ticket is always commented and left open — the loop halts loudly,
never silently skips.

## Usage

```bash
# Interactive, one phase, checkpoint mode — review the prep before GO:
/auto-matt --phase 3

# AFK supervisor: dry-run a phase, then the whole roadmap:
ralph.sh --dir /Users/z/Documents/open-intel-saas --phase 3 --watch
ralph.sh --dir /Users/z/Documents/open-intel-saas --phase all --afk --max-attempts 0 --watch
```

State and resume: the **GitHub tracker is the source of truth** (tickets,
blocking edges, phase tracking issues, GO comments). `.auto-matt/roadmap.json`
is a rebuildable local cache — deleting it loses nothing. A crashed or
restarted run rebuilds position from the tracker and never redoes finished
work. One phase-mode run per working tree at a time.

Push scope: phase mode commits to the yaml's `branch:` only and pushes only
when `push: true`. Merging to `product/open-intel-v1` stays human, per phase,
at each checkpoint review.

## This repo's configuration

Phases 3–8 are `auto`; phases 9–10 are `gated` (Stripe credentials, pen test,
secret drills become `ready-for-human` tickets). Spec anchors point into
`planning/open-notebook-multiteam-saas-plan-3.md` §16. The gate is
`make ci-local`, which mirrors `.github/workflows/product-ci.yml`.
