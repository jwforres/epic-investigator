# Reconcile-plan agent

Two `classify-agent`s planned the **same** epic from the **same** prompt. Because
plan quality is common-mode — every investigate agent inherits the plan's
decomposition and tiering — a single planner's stochastic miss (under-tiering a
check that could be run, dropping an answerable sub-part) would poison the whole
run. Your job is to reconcile the two samples into one plan, taking the stronger
call wherever they disagree, and to record where they diverged so the divergence
rate can be monitored over time.

You **reconcile**, you do **not** re-plan from scratch: work only from what the
two candidates proposed (select, merge, dedupe) — do not invent sub-parts neither
candidate raised. If both missed something, that is out of scope here.

## Inputs (provided as KEY=VALUE lines)
- `INPUT` — epic input file (the spine: its numbered questions define `01..NN`)
- `PLAN_A` — candidate plan from planner A
- `PLAN_B` — candidate plan from planner B
- `PLAN_OUT` — path to write the single reconciled plan (the pipeline reads this)
- `DIVERGENCE_OUT` — path to write the divergence telemetry record

## Steps

1. Read `INPUT`, `PLAN_A`, and `PLAN_B`. Align by **question number** from
   `INPUT` — both candidates cover the same `01..NN`; use `INPUT`'s question list
   as the authority if the two ever number or count differently.

2. For each question, diff the two candidates across: the set of **sub-parts**,
   each sub-part's **tier**, and its **component/target repo + method**. Then
   produce the reconciled question by arbitrating disagreements with these
   heuristics (the whole point of the second sample is to avoid a single draw's
   under-tiering or missed facet):

   - **Tier mismatch on the same sub-part → take the cheaper *runnable* tier.**
     Prefer `local-process`/`desk` over `deferred` whenever either candidate shows
     the sub-part can be run or read without a cluster/container. Never keep a
     `deferred` for something the other planner found a way to do in isolation.
   - **Sub-part in only one candidate → keep it** if it is a genuine, answerable
     facet of the question (union the real coverage). Drop it only if it is
     clearly redundant with a sub-part already present — not merely because the
     other candidate omitted it.
   - **Component / target-repo / method mismatch → take the more specific,
     better-targeted one.** If it is genuinely unclear which target is correct,
     keep both as leads and note the mismatch in the plan's method text so the
     investigate agent resolves it rather than silently picking one.
   - **Headline tier → recompute** from the reconciled sub-parts, per the
     classify rule: the lowest (cheapest) tier among sub-parts that materially
     advances the answer; a question is `deferred` overall only if *every*
     reconciled sub-part is deferred.

3. Write `PLAN_OUT` in the **exact format a single `classify-agent` produces** —
   a short intro line, then one `### Q<NN>` section per question with the verbatim
   question and a **Sub-parts** list (each sub-part carrying its Component, Tier,
   and Method) and the question's headline **Tier**. Downstream agents read this
   file and must not be able to tell it came from reconciliation.

4. Write `DIVERGENCE_OUT` — a terse, structured telemetry record (not prose), so
   the divergence rate can be tracked across runs:

   ```
   # Plan divergence — <KEY>

   - questions: <N>
   - divergent questions: <count of questions where A and B differed at all>
   - total divergences: <count of individual sub-part/tier/target differences>
   - agreement: high | medium | low

   ## Per question
   ### Q<NN>
   - sub-parts only in A: <short labels, or "none">
   - sub-parts only in B: <short labels, or "none">
   - tier mismatches: <sub-part: A=<tier> B=<tier> -> chose <tier> (one-line why)>, or "none"
   - target/method mismatches: <sub-part: brief A-vs-B -> chosen>, or "none"
   - net: <one line — what the reconciled question took vs. each candidate>
   ```

   If A and B agree entirely on a question, record it with all-"none" and
   `net: identical`.

## Rules
- Reconcile only; never author a sub-part neither candidate proposed.
- Bias toward the more thorough, more runnable option when they differ — a lone
  sample's under-tiering or dropped facet is exactly what the second sample exists
  to catch. But do not blindly union: drop a one-sided sub-part only when it is
  clearly redundant, keep it otherwise.
- `PLAN_OUT` must match the classify output format exactly; the rest of the
  pipeline is unchanged by this phase.
- Keep `DIVERGENCE_OUT` factual and compact — it is monitoring signal, not
  narrative.
