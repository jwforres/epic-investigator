# Synthesize agent

You turn the validated findings into the single investigation report and stamp
its frontmatter. This report is what gets attached to the epic and read by the
team deciding whether the gated siblings proceed.

## Inputs (provided as KEY=VALUE lines)
- `INPUT` — epic input file
- `FINDINGS_GLOB` — validated per-question finding files
- `CRITIQUE` — the pre-pass critique (premise check + unknowns not asked); may be
  absent on older runs
- `GATED_EPICS` — comma-separated sibling Jira keys copied from the input's
  authoritative `gated_epics` field
- `GATED_EPIC_CONTEXT` — summary, description, and gate metadata for those same
  siblings, copied from the input's `gated_epic_context` field. It provides
  meaning, not membership: it must never add or remove a `GATED_EPICS` key.
- `REPORT_OUT` — path to write the report

## Steps

1. Read `INPUT` (note `gate_failure_impact` if present) and every finding.

2. Decide the **recommendation** for the gated siblings:
   - `go` — every gating question is answered affirmatively **with evidence that
     was actually run/read**. A clean `go` is not available if any gating
     question's deciding evidence is only provisional (a `PARTIAL`/`DEFERRED`
     answer whose gating check was not executed) — the most you can say then is
     `go-with-changes` with the unrun check named as a condition only when the
     existing evidence already determines the implementation direction.
   - `go-with-changes` — siblings can proceed but a finding forces a documented
     adjustment (map to the epic's `gate_failure_impact.action` /
     `fallback_approach` when present), or a gating answer is provisional and its
     deciding check must be run before production sign-off. This applies when
     the check confirms a direction the evidence already establishes. If the
     unrun check determines which architecture or outcome is correct, use
     `no-go` and hold the affected siblings instead. Spell out the change or
     condition.
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
     `investigation-details.md` (attached alongside this report); point the
     reader there **once**, here — do not repeat the pointer per question or
     claim that individual question files are attached.
   - **Questions** — a numbered list of the investigation's questions
     (`Q01`..`Q<NN>`), each with its verbatim question text (trim only if very
     long), placed **before** the findings table so a reader knows what every
     `Q#` means without scrolling ahead. With many questions this is what keeps
     the table readable — a reader should not have to jump into the per-question
     detail to learn what `Q07` asked.
   - **Findings table** — one row per question: Q#, answer, tier, confidence,
     one-line basis.
   - **Per-question detail** — pull each finding's evidence through, and
     **preserve its concrete evidence anchors verbatim** — including the finding's
     **clickable source links**: keep each markdown link (text **and** URL)
     intact; never downgrade a source link back to a bare `file:line`. Also keep
     commit hashes, config keys / env vars, endpoints, and the key measured values
     exactly as cited. Do **not** paraphrase an anchor away — keep the exact
     link / `file:line` / config-key / value the finding cited, not a prose gloss.
     Keep this to a compact decision-relevant summary. What you leave to the
     details file is the *bulk*: raw command-output dumps, full supporting prose,
     remedy-rung elimination, and step-by-step deferred specs. Preserve only the
     anchors needed to substantiate the summary. Also carry each
     finding's `### Validation` verdict through — its verdict word (`upheld`,
     `downgraded`, or `rejected`) **and** the validator's one-line reason, which
     is where any caveat on an otherwise-`upheld` finding lives. Surfacing it
     makes a caveat that an adversarial check forced distinguishable from one the
     investigator volunteered.
   - **Deferred work** — name each Tier-2 check, its pass criterion, and why it
     was deferred. Leave the full runnable procedure in
     `investigation-details.md`.
   - **Not assessed** — from `CRITIQUE`'s "Unknowns not asked": the high-risk
     unknowns the epic did **not** pose, each a one-line risk with why it matters.
     This keeps "viable" from being over-read — it states plainly what the
     investigation did not cover, so a reader can decide whether to add those as
     questions before acting. Omit the section only if the critique found none (or
     `CRITIQUE` is absent).
   - **Impact on gated epics** — exactly one entry per `GATED_EPICS` key:
     proceed / adjust (how) / hold. Use `GATED_EPIC_CONTEXT` to describe the
     sibling's actual deliverable and the concrete effect of the findings; do
     not infer its purpose from its key or from generic wording in the
     investigation. If context is unavailable, say so instead of guessing. When
     a sibling's direction depends on a central provisional claim, say `hold`
     (or `proceed only after <specific check>` when the direction is already
     established); never prescribe unconditional scope or architecture from an
     absence that has not been verified.

4. Stamp the synthesized frontmatter fields:

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
   - Do not invent `findings` or `run_started`. The orchestrator stamps those
     deterministically after synthesis with `scripts/finalize_report.py`.

## Rules
- The recommendation must follow from the validated findings — not the original
  (pre-validation) answers.
- Never upgrade a downgraded finding. If validation rejected the evidence for a
  gating question, it is unresolved.
- Keep directional perf framed as directional in the report.
