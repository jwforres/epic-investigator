---
name: epic-investigate
description: Run the unknowns in an Investigation-type epic to ground its gated sibling epics. Resolves each question at the cheapest sufficient evidence tier (desk research, local-process execution, or deferred), adversarially validates findings, and writes a single status report back to the epic. Non-interactive.
user-invocable: true
allowed-tools: Glob, Read, Bash, Agent
---

You are a non-interactive investigation pipeline. Do not ask questions or wait
for confirmation. Make all decisions autonomously and resolve every question to
the best evidence the execution sandbox allows.

## What an investigation is

An Investigation epic poses a scoped set of **unknowns** (a numbered list of
questions) that **gate downstream sibling epics**. Your job is to answer each
question with evidence, then issue a single go / no-go recommendation for the
epics it gates. You do not rewrite sibling epics — that is a downstream step.

### Evidence tiers

Resolve each question at the **cheapest tier that can actually answer it**:

- **Tier 0 — Desk.** Read upstream source, `.context/architecture-context/`,
  docs, and the web. Answers interface/API coverage, maturity, "does X exist".
- **Tier 1 — Local process.** Run the component as a downloaded **binary** or a
  pip/npm-installed **library** as a localhost process and probe it. Answers
  "do these actually integrate", real op coverage, *directional* perf. Latency
  from this sandbox is **directional, never a production benchmark** — say so.
- **Tier 2 — Deferred.** Anything needing a **container runtime** (podman/
  docker), a **live OpenShift cluster**, or production-scale infra. Do **not**
  attempt it. Emit a concrete, runnable test/benchmark spec plus a provisional
  answer from Tier 0/1 evidence.

Discover capability **live**: attempt the Tier-1 probe; if the sandbox can't
install the package, bind a port, reach the network, or the work needs a
container/cluster, degrade to Tier 2 and record *why*. Never fabricate a result.

## Setup

Parse `$ARGUMENTS` for:
- Explicit Jira epic keys (e.g. `RHAISTRAT-1234-E001`)
- `--from-file <path>` — ingest a local epic-task file instead of Jira
- `--no-jira` — write the report locally but do not publish to the epic
- `--data-dir <path>` — defaults to `artifacts`

### Init

```bash
python3 scripts/state.py init tmp/investigate-state.yaml \
    started=$(python3 scripts/state.py timestamp)
```

### Bootstrap architecture context

Desk-tier research relies on the RHOAI architecture context. Fetch it into
`.context/architecture-context/` (safe to re-run; retry once on failure):

```bash
bash scripts/fetch-architecture-context.sh
```

If it fails twice, continue anyway — agents fall back to upstream source + web
and note the absence in their findings.

### Fetch the epic(s)

For each key (or the `--from-file` source):

```bash
python3 scripts/fetch_epic.py <KEY>            # or: --from-file <path>
```

This writes `artifacts/investigations/<KEY>-input.md`. Read it. The body holds
the Scope (numbered questions), Acceptance Criteria, and HLR Traceability.

Identify the **gated sibling epics**: the epics whose `gated_by` points at this
one (from the parent decomposition), or as named in the epic body. Record them.

## Per-epic pipeline

Run these phases in order for each epic. Persist progress to
`tmp/investigate-state.yaml` so it survives compression.

### Phase 1 · CLASSIFY (1 agent)

Launch one `classify-agent`:

```
INPUT=artifacts/investigations/<KEY>-input.md
PLAN_OUT=artifacts/investigations/<KEY>-plan.md

Read skills/epic-investigate/prompts/classify-agent.md and follow it exactly.
```

It writes a plan: each question tagged with its tier and method. Read it to get
the question count `N`.

### Phase 2 · INVESTIGATE (N agents, parallel)

Launch one `investigate-agent` **per question**, concurrently (multiple Agent
calls in one message). Each writes `artifacts/investigations/<KEY>-q<NN>.md`:

```
INPUT=artifacts/investigations/<KEY>-input.md
PLAN=artifacts/investigations/<KEY>-plan.md
QUESTION_NUM=<NN>
FINDING_OUT=artifacts/investigations/<KEY>-q<NN>.md

Read skills/epic-investigate/prompts/investigate-agent.md and follow it exactly.
```

Wait for all to finish before continuing.

### Phase 3 · VALIDATE (1 agent)

Launch one `validate-agent` to adversarially re-check every finding against its
cited evidence and downgrade anything unsupported:

```
INPUT=artifacts/investigations/<KEY>-input.md
FINDINGS_GLOB=artifacts/investigations/<KEY>-q*.md
Read skills/epic-investigate/prompts/validate-agent.md and follow it exactly.
```

**Re-investigation backstop.** After validation, scan the finding files for any
`### Validation` verdict of `deferral-not-established`. For each, re-launch a
single `investigate-agent` for that question (same vars as Phase 2), instructing
it to read the specific source artifact the validator named rather than stop at
the digest. Re-run validation on the updated finding. Do this at most once per
question, then proceed — a still-unresolved deferral stays `deferred` with its
reason. This is the backstop for a deferral the classifier waved through.

### Phase 4 · SYNTHESIZE (1 agent)

Launch one `synthesize-agent` to roll findings into the report and stamp
frontmatter (status, recommendation, rollup counts) via
`scripts/frontmatter.py`:

```
INPUT=artifacts/investigations/<KEY>-input.md
FINDINGS_GLOB=artifacts/investigations/<KEY>-q*.md
GATED_EPICS=<comma-separated sibling ids>
REPORT_OUT=artifacts/investigations/<KEY>-investigation.md
Read skills/epic-investigate/prompts/synthesize-agent.md and follow it exactly.
```

### Phase 5 · PUBLISH

Unless `--no-jira`:

```bash
python3 scripts/attach_report.py <KEY> \
    --report artifacts/investigations/<KEY>-investigation.md
```

This attaches the report as the well-known `investigation-report.md` and applies
the status label. Skip for `--from-file` inputs without a real Jira key.

## Teardown

After all epics finish, print a one-line summary per epic: `<KEY> status=<…>
recommendation=<…> resolved=<n>/<total> deferred=<n>`.

$ARGUMENTS
