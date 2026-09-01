#!/usr/bin/env python3
"""Stamp deterministic run metadata onto a synthesized investigation report."""

import argparse
import glob
import re
import sys

from artifact_utils import (
    read_frontmatter_validated,
    update_frontmatter,
    ValidationError,
)


QUESTION_RE = re.compile(r"^## Q(\d+):", re.MULTILINE)
FIELD_RE = {
    "tier": re.compile(r"^- \*\*Tiers executed:\*\*\s*(.+)$", re.MULTILINE),
    "answer": re.compile(r"^- \*\*Answer:\*\*\s*(YES|NO|PARTIAL|DEFERRED)\s*$",
                         re.MULTILINE),
    "confidence": re.compile(r"^- \*\*Confidence:\*\*\s*(high|medium|low)\s*$",
                             re.MULTILINE),
}


def _finding(path):
    with open(path, encoding="utf-8") as fh:
        content = fh.read()

    question_match = QUESTION_RE.search(content)
    values = {name: pattern.search(content) for name, pattern in FIELD_RE.items()}
    missing = [name for name, match in values.items() if match is None]
    if question_match is None:
        missing.insert(0, "question")
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")

    number = int(question_match.group(1))
    return number, {
        "question": f"Q{number:02d}",
        "tier": values["tier"].group(1).strip(),
        "answer": values["answer"].group(1),
        "confidence": values["confidence"].group(1),
    }


def finalize(report, findings_glob, state):
    findings = [_finding(path) for path in glob.glob(findings_glob)]
    findings.sort(key=lambda item: item[0])
    numbers = [number for number, _ in findings]
    if len(numbers) != len(set(numbers)):
        raise ValueError("duplicate question numbers in finding files")

    meta, _ = read_frontmatter_validated(report, "investigation-report")
    resolved = meta.get("questions_resolved", 0)
    if meta["status"] == "complete" and len(findings) != resolved:
        raise ValueError(
            f"complete report has {resolved} resolved questions but "
            f"{len(findings)} finding files")

    started = None
    with open(state, encoding="utf-8") as fh:
        for line in fh:
            key, separator, value = line.partition(":")
            if separator and key.strip() == "started":
                started = value.strip().strip("'\"")
                break
    if not started:
        raise ValueError(f"{state}: missing started timestamp")

    update_frontmatter(
        report,
        {
            "findings": [finding for _, finding in findings],
            "run_started": started,
        },
        "investigation-report",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Finalize deterministic investigation report metadata")
    parser.add_argument("--report", required=True)
    parser.add_argument("--findings-glob", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    try:
        finalize(args.report, args.findings_glob, args.state)
    except (OSError, ValueError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: finalized {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
