#!/usr/bin/env python3
"""Concatenate the per-question finding files into a single evidence detail file.

The investigation report (`<KEY>-investigation.md`) is the lean decision
document: verdict, findings table, per-question synthesis, gated-epic impact.
It deliberately does not carry the full evidence — raw command output, complete
remedy-rung elimination, step-by-step deferred specs, validation prose.

This script produces the companion `<KEY>-investigation-details.md`: a faithful,
mechanical concatenation of every `<KEY>-q<NN>.md` finding, in question order,
under one title. It is a *copy*, not a re-synthesis — no paraphrasing, so the
citations and captured output survive verbatim. Attach it alongside the report
so anyone (human or a downstream agent) can inspect the proof behind a verdict.

    python3 scripts/build_details.py RHAISTRAT-1234-E001
    python3 scripts/build_details.py RHAISTRAT-1234-E001 --data-dir artifacts

Writes `<data-dir>/investigations/<KEY>-investigation-details.md` and prints its
path. If there are no finding files (e.g. a blocked/errored investigation),
it writes nothing and warns — publishing still proceeds without a details file.
"""

import argparse
import glob
import os
import re
import sys


# A finding file is exactly `<KEY>-q<NN>.md`: `-q`, digits, `.md`, nothing else.
# The same pattern gates inclusion and yields the sort number, so the set of
# files concatenated is exactly the set that sorts cleanly — no ancillary file
# (e.g. `<KEY>-q01-notes.md`) sneaks in and lands out of order.
_FINDING_RE = re.compile(r"-q(\d+)\.md$")


def find_finding_files(investigations_dir, key):
    """The `<KEY>-q<NN>.md` findings, question-ordered (numeric, not lexical).

    Matches only the numbered per-question files — never the report, plan,
    input, an ancillary `<KEY>-q<NN>-*.md`, or a `<KEY>-q<NN>-evidence/` data
    directory.
    """
    matched = []
    for path in glob.glob(os.path.join(investigations_dir, f"{key}-q[0-9]*.md")):
        m = _FINDING_RE.search(os.path.basename(path))
        if m and os.path.isfile(path):
            matched.append((int(m.group(1)), path))
    return [path for _, path in sorted(matched)]


def build_details(investigations_dir, key):
    """Write the concatenated details file. Returns (out_path, n_findings), or
    (None, 0) when there are no findings to concatenate (nothing is written)."""
    findings = find_finding_files(investigations_dir, key)
    if not findings:
        return None, 0

    parts = [
        f"# Investigation evidence detail: {key}",
        "",
        "Full per-question evidence backing the investigation report "
        "(`investigation-report.md`). Each section is the finding file for one "
        "question, reproduced verbatim — citations, captured command output, "
        "remedy-rung elimination, deferred specs, and the adversarial "
        "`Validation` verdict. The report summarizes these; this file is the "
        "proof. One section per question, in order.",
        "",
    ]
    for path in findings:
        with open(path, encoding="utf-8") as fh:
            body = fh.read().strip("\n")
        parts.append("---")
        parts.append("")
        parts.append(body)
        parts.append("")

    out_path = os.path.join(investigations_dir,
                            f"{key}-investigation-details.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts).rstrip("\n") + "\n")
    return out_path, len(findings)


def main():
    ap = argparse.ArgumentParser(
        description="Concatenate per-question findings into the details file")
    ap.add_argument("key", help="Investigation epic key (e.g. RHAISTRAT-1234-E001)")
    ap.add_argument("--data-dir", default="artifacts",
                    help="Artifacts root (default: artifacts)")
    args = ap.parse_args()

    investigations_dir = os.path.join(args.data_dir, "investigations")
    out_path, n = build_details(investigations_dir, args.key)
    if out_path is None:
        # A blocked/errored investigation may legitimately have no findings;
        # that is not an error — publish still proceeds without a details file.
        print(f"WARN: no {args.key}-q<NN>.md findings in {investigations_dir}; "
              f"no details file written", file=sys.stderr)
        return
    print(f"OK: wrote {out_path} from {n} finding file(s)")


if __name__ == "__main__":
    main()
