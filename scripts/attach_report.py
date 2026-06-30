#!/usr/bin/env python3
"""Write an investigation report back to its Jira epic.

Attaches the report under a single WELL-KNOWN name so downstream tooling and
humans always know where to look. Re-runs replace the prior attachment rather
than piling up duplicates. Applies a status label mirroring epic-creator's
`decomp-ready` convention.

    python3 scripts/attach_report.py RHAISTRAT-1234-E001 \
        --report artifacts/investigations/RHAISTRAT-1234-E001-investigation.md

Use --dry-run to validate and preview without touching Jira.
"""

import argparse
import sys

from artifact_utils import read_frontmatter_validated, ValidationError
import jira_utils

# The constant filename every investigation report is attached under.
WELL_KNOWN_NAME = "investigation-report.md"

# status (run lifecycle) -> label applied to the epic
STATUS_LABELS = {
    "complete": "investigation-complete",
    "blocked": "investigation-blocked",
    "error": "investigation-error",
}
ALL_LABELS = set(STATUS_LABELS.values())


def _delete_existing(server, user, token, key):
    """Remove any prior attachment with the well-known name (best effort)."""
    issue = jira_utils.get_issue(server, user, token, key, fields=["attachment"])
    for att in issue.get("fields", {}).get("attachment", []) or []:
        if att.get("filename") == WELL_KNOWN_NAME:
            jira_utils.api_call_with_retry(
                server, f"/rest/api/3/attachment/{att['id']}",
                user, token, method="DELETE")


def main():
    ap = argparse.ArgumentParser(description="Attach an investigation report")
    ap.add_argument("key", help="Jira epic key")
    ap.add_argument("--report", required=True, help="Path to the report markdown")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    meta, _ = read_frontmatter_validated(args.report, "investigation-report")
    status = meta["status"]
    if status == "in_progress":
        print("ERROR: report status is still 'in_progress'; not publishing.",
              file=sys.stderr)
        sys.exit(2)

    with open(args.report, encoding="utf-8") as fh:
        content = fh.read()

    label = STATUS_LABELS.get(status)
    print(f"epic={args.key} status={status} "
          f"recommendation={meta.get('recommendation')} label={label} "
          f"attach_as={WELL_KNOWN_NAME}")
    if args.dry_run:
        return

    server, user, token = jira_utils.require_env()
    _delete_existing(server, user, token, args.key)
    jira_utils.add_attachment(server, user, token, args.key,
                              WELL_KNOWN_NAME, content)
    if label:
        # Clear any stale status label from a prior run, then apply the current.
        jira_utils.remove_labels(server, user, token, args.key,
                                 list(ALL_LABELS - {label}))
        jira_utils.add_labels(server, user, token, args.key, [label])
    print(f"OK: attached {WELL_KNOWN_NAME} to {args.key}")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
