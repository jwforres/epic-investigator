# epic-investigator

Runs the **Investigation-type epics** produced by
[epic-creator](../epic-creator). An Investigation epic is a scoped set of
technical unknowns that gate downstream sibling epics. This tool resolves those
unknowns with evidence, then writes a single go/no-go report back to the epic.

It is the execution counterpart to epic-creator's decomposition, designed to run
as its own CI job — one invocation per Investigation epic.

## How it works

The `epic-investigate` skill runs four phases per epic:

1. **Classify** — extract the numbered questions and tag each with the cheapest
   evidence tier that can answer it (desk / local-process / deferred).
2. **Investigate** — one agent per question gathers evidence at its tier.
3. **Validate** — an adversarial pass downgrades any answer its evidence doesn't
   support.
4. **Synthesize** — roll findings into a report + a go/no-go for the siblings.

Fetching the epic and publishing the report are **CI steps outside the skill**
(see the credential boundary below).

### Credential boundary

The skill never touches Jira. Jira I/O is split into a pre-step and a post-step
so the phases that clone and read untrusted upstream source never have
`JIRA_TOKEN` in their environment:

```bash
# 1. pre-step (needs Jira creds) — fetch the epic to disk
python3 scripts/fetch_epic.py RHAISTRAT-1234-E001

# 2. the skill (no creds) — investigate and write the report to disk
claude -p "/epic-investigate RHAISTRAT-1234-E001"

# 3. post-step (needs Jira creds) — publish the report
python3 scripts/attach_report.py RHAISTRAT-1234-E001 \
    --report artifacts/investigations/RHAISTRAT-1234-E001-investigation.md
```

The report's frontmatter is the handoff. Step 3 reads it for status and
recommendation, refuses an `in_progress` or internally inconsistent report, and
refuses to attach a report whose `jira_key` doesn't match the key it was given.

### Evidence tiers

| Tier | Method | Runs in the sandbox? |
|------|--------|----------------------|
| 0 · Desk | source audit, architecture-context, docs, web | yes |
| 1 · Local process | run a binary / pip-or-npm library and probe it | yes — **binary-only, no containers** |
| 2 · Deferred | needs a container runtime, a cluster, or prod scale | no — emits a runnable spec |

Tier-1 capability is discovered **live**: if the sandbox can't install/run/reach
what a probe needs, the question degrades to Tier 2 with the reason recorded.
Tier-1 perf numbers are directional, never production benchmarks.

## Usage

```bash
# From Jira (CI path) — run the fetch pre-step first, then:
claude
> /epic-investigate RHAISTRAT-1234-E001

# From a local epic-task file (dev path) — no pre-step, no credentials at all
> /epic-investigate --from-file ../epic-creator/artifacts/epic-tasks/RHAISTRAT-1234-E001.md
```

The Jira path expects `artifacts/investigations/<KEY>-input.md` to already exist;
the skill stops and says so if the fetch step hasn't run. `--from-file` reads a
local file, so the skill ingests it directly.

Set `JIRA_SERVER`, `JIRA_USER`, `JIRA_TOKEN` for the fetch and publish steps
only — not for the skill itself.

## Layout

```
skills/epic-investigate/   # SKILL.md + per-phase agent prompts
scripts/                   # frontmatter / state / Jira I/O utilities
artifacts/investigations/  # per-epic working files + the report (gitignored)
```

## Scope (v1)

Report-only — issues a recommendation, does not rewrite sibling epics. Tier 2
(cluster / container) execution is deferred-with-spec, not run.
