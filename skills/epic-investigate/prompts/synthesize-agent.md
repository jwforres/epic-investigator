# Synthesize agent

You turn the validated findings into the single investigation report and stamp
its frontmatter. This report is what gets attached to the epic and read by the
team deciding whether the gated siblings proceed.

## Inputs (provided as KEY=VALUE lines)
- `INPUT` — epic input file
- `FINDINGS_GLOB` — validated per-question finding files
- `CRITIQUE` — the pre-pass critique (premise check + unknowns not asked); may be
  absent on older runs
- `GATED_EPICS` — comma-separated sibling epic ids this investigation gates
- `REPORT_OUT` — path to write the report

## Steps

1. Read `INPUT` (note `gate_failure_impact` if present) and every finding.

2. Decide the **recommendation** for the gated siblings:
   - `go` — every gating question is answered affirmatively **with evidence that
     was actually run/read**. A clean `go` is not available if any gating
     question's deciding evidence is only provisional (a `PARTIAL`/`DEFERRED`
     answer whose gating check was not executed) — the most you can say then is
     `go-with-changes` with the unrun check named as a condition.
   - `go-with-changes` — siblings can proceed but a finding forces a documented
     adjustment (map to the epic's `gate_failure_impact.action` /
     `fallback_approach` when present), or a gating answer is provisional and its
     deciding check must be run before production sign-off. Spell out the change
     or the condition.
   - `no-go` — a gating question came back NO, or a question the siblings depend
     on is unresolved/`DEFERRED` such that proceeding is unsafe.
   Deferred-but-non-blocking questions do not force `no-go`; call them out as
   follow-ups instead.

3. Write `REPORT_OUT` body:
   - **Summary** — the recommendation and the one or two findings that drove it.
     Immediately after the recommendation, add one blunt **"What this rests on"**
     line for the decision-maker who will anchor on the verdict word: how many
     answers are provisional (gating evidence deferred/unrun), how many deferred
     checks remain, the key unverified assumptions the recommendation depends on,
     and whether the critique flagged high-risk unknowns the epic never asked
     (see Not assessed). Keep it next to the verdict, not buried in the table — a
     reader should not have to reconstruct "N of M answers are still unproven"
     from the rows.
     Note that full per-question evidence lives in the companion
     `<KEY>-investigation-details.md` (attached alongside this report); point
     the reader there **once**, here — do not repeat the pointer per question.
   - **Findings table** — one row per question: Q#, answer, tier, confidence,
     one-line basis.
   - **Per-question detail** — pull each finding's evidence through, and
     **preserve its concrete evidence anchors verbatim**: file:line references,
     commit hashes, config keys / env vars, endpoints, and the key measured
     values. Do **not** paraphrase an anchor away — keep the exact
     `file:line` / config-key / value the finding cited, not a prose gloss of it.
     Every claim must be verifiable from the report alone. What you leave to the
     details file is the
     *bulk*, not the anchors: raw command-output dumps, the full remedy-rung
     elimination prose, and step-by-step deferred specs. Also carry each
     finding's `### Validation` verdict through — its verdict word (`upheld`,
     `downgraded`, or `rejected`) **and** the validator's one-line reason, which
     is where any caveat on an otherwise-`upheld` finding lives. Surfacing it
     makes a caveat that an adversarial check forced distinguishable from one the
     investigator volunteered.
   - **Deferred work** — collect every Tier-2 spec so a cluster owner can run
     them, with the reason each was deferred.
   - **Not assessed** — from `CRITIQUE`'s "Unknowns not asked": the high-risk
     unknowns the epic did **not** pose, each a one-line risk with why it matters.
     This keeps "viable" from being over-read — it states plainly what the
     investigation did not cover, so a reader can decide whether to add those as
     questions before acting. Omit the section only if the critique found none (or
     `CRITIQUE` is absent).
   - **Impact on gated epics** — per sibling: proceed / adjust (how) / hold.

4. Stamp frontmatter with the validated rollup (build the findings JSON, then):

   ```bash
   python3 scripts/frontmatter.py set <REPORT_OUT> \
       epic_id=<id> title="<title>" parent_strat=<RHAISTRAT-N> jira_key=<key> \
       status=complete recommendation=<go|go-with-changes|no-go> \
       questions_total=<N> questions_resolved=<n> questions_deferred=<n> \
       questions_provisional=<p> \
       deferred_to_cluster=<true|false> \
       evidence_tiers_used='["desk","local-process","deferred"]' \
       gated_epics='["<id>", "..."]' \
       run_completed=$(python3 scripts/state.py timestamp)
   ```

   - `questions_resolved` counts questions that produced a finding at all
     (completeness); `questions_provisional` counts the subset whose **headline
     answer is `PARTIAL`/`DEFERRED`** because the deciding evidence was not run.
     Keep them distinct: a run can be `N/N resolved` and still have several
     provisional answers, and the report must not read as `N/N verified`.
   - `status=complete` requires exactly one finding file per question
     (`questions_resolved == questions_total`, and `questions_total` = the number
     of questions in the plan). If any question's finding is missing or empty (a
     dead investigate agent), set `status=error`, set `error` to name the missing
     question(s), and set `questions_resolved` to the actual count — do **not**
     stamp `complete`. (`attach_report.py` also rejects a `complete` report whose
     `questions_resolved != questions_total`, so an inconsistent run cannot be
     published as complete.)
   - Set `status=blocked` (instead of `complete`) only if a gating question
     could not be resolved at all and the recommendation is forced to `no-go`
     for lack of evidence rather than negative evidence.
   - `evidence_tiers_used`, `gated_epics`, and list fields take JSON arrays.
   - Omit `jira_key` for `--from-file` runs without a real key.

## Rules
- The recommendation must follow from the validated findings — not the original
  (pre-validation) answers.
- Never upgrade a downgraded finding. If validation rejected the evidence for a
  gating question, it is unresolved.
- Keep directional perf framed as directional in the report.
