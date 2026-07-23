# Epic Investigator

A skill for **running** the Investigation-type epics produced by
[epic-creator](../epic-creator). An Investigation epic poses a scoped set of
unknowns that gate downstream sibling epics; this skill resolves those unknowns
with evidence and writes a single status report back to the epic.

This is the execution counterpart to epic-creator's decomposition: epic-creator
*writes* Investigation epics, epic-investigator *runs* them. It is intended to
run as its own CI job, one invocation per Investigation epic.

## Evidence tiers

Every question is answered at the cheapest tier that can actually answer it:

- **Tier 0 — Desk:** upstream source audit, `.context/architecture-context/`,
  docs, web. No execution.
- **Tier 1 — Local process:** run the component as a downloaded **binary** or a
  pip/npm **library** as a localhost process and probe it. **No container
  runtime** — the execution sandbox (OpenShell) is assumed not to provide
  podman/docker. Capability is discovered **live**; if a probe can't run, it
  degrades to Tier 2. Latency/throughput here is *directional, not a production
  benchmark*.
- **Tier 2 — Deferred:** anything needing a container runtime, a live OpenShift
  cluster, or production-scale infra. Not executed — the report emits a runnable
  spec plus a provisional answer.

## Artifact Conventions

All skills read from and write to the `artifacts/` directory.

```
artifacts/
  investigations/
    <EPIC-KEY>-input.md            # Fetched epic (Scope, questions, ACs)
    <EPIC-KEY>-critique.md         # Pre-pass: premise check + unknowns not asked
    <EPIC-KEY>-plan.md             # Per-question tier classification
    <EPIC-KEY>-q01.md … q<NN>.md   # Per-question findings (+ validation)
    <EPIC-KEY>-investigation.md    # The report (attached to the epic)
```

### Frontmatter

Task and report files use YAML frontmatter. Skills must use
`scripts/frontmatter.py` to read schemas, set fields, and read validated data —
never write YAML by hand.

```bash
python3 scripts/frontmatter.py schema investigation-report
python3 scripts/frontmatter.py set <path> field=value ...
python3 scripts/frontmatter.py read <path>
```

The report's frontmatter `status` (`in_progress` | `complete` | `blocked` |
`error`) is the **single source of truth for the run's current state**;
`recommendation` (`go` | `go-with-changes` | `no-go`) is the verdict for the
gated siblings.

### State Persistence

Long-running skills use `scripts/state.py` to persist state to `tmp/` so it
survives context compression — never inline `cat`/`echo`/`mkdir`.

## Jira Integration

- **Read:** `scripts/fetch_epic.py` fetches an Investigation epic by key (or
  ingests a local epic-task file via `--from-file`).
- **Write-back:** `scripts/attach_report.py` attaches the report under the
  well-known name `investigation-report.md` (replacing any prior copy) and
  applies a status label (`investigation-complete` / `-blocked` / `-error`).

Required environment variables:

```
JIRA_SERVER=https://your-site.atlassian.net
JIRA_USER=your-email@example.com
JIRA_TOKEN=your-api-token
```

## Scope (v1)

- **Report-only.** This skill issues a go/no-go for the gated siblings; it does
  **not** rewrite them. Acting on the recommendation (re-decompose/revise) is a
  separate downstream step.
- **Tier 0 + Tier 1 execute; Tier 2 is deferred with a spec.** Cluster and
  container-runtime execution are out of scope for v1.
