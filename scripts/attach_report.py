#!/usr/bin/env python3
"""Write an investigation report back to its Jira epic.

Attaches the report under a single WELL-KNOWN name so downstream tooling and
humans always know where to look. Re-runs replace the prior attachment rather
than piling up duplicates. Applies a status label mirroring epic-creator's
`decomp-ready` convention.

    python3 scripts/attach_report.py RHAISTRAT-1234-E001 \
        --report artifacts/investigations/RHAISTRAT-1234-E001-investigation.md

If a companion `<KEY>-investigation-details.md` sits next to the report (written
by `scripts/build_details.py`), it is attached too, under the well-known name
`investigation-details.md`, so the full per-question evidence travels with the
decision report.

Use --dry-run to validate and preview without touching Jira.
"""

import argparse
import os
import sys

from artifact_utils import read_frontmatter_validated, ValidationError
import jira_utils

# The constant filename every investigation report is attached under.
WELL_KNOWN_NAME = "investigation-report.md"
# The companion evidence file, attached under this name when present next to it.
DETAILS_WELL_KNOWN_NAME = "investigation-details.md"

# status (run lifecycle) -> label applied to the epic
STATUS_LABELS = {
    "complete": "investigation-complete",
    "blocked": "investigation-blocked",
    "error": "investigation-error",
}
ALL_LABELS = set(STATUS_LABELS.values())


def _delete_existing(server, user, token, key, names, exclude_ids=frozenset()):
    """Remove prior attachments with one of the well-known names (best effort).

    `exclude_ids` protects attachments we just uploaded — we replace by
    uploading the new copy first, then deleting the *old* ones, so a failed
    upload can never leave the epic with no report at all.
    """
    issue = jira_utils.get_issue(server, user, token, key, fields=["attachment"])
    for att in issue.get("fields", {}).get("attachment", []) or []:
        if att.get("filename") in names and att.get("id") not in exclude_ids:
            jira_utils.api_call_with_retry(
                server, f"/rest/api/3/attachment/{att['id']}",
                user, token, method="DELETE")


def _details_path(report_path):
    """Path to the companion details file for a report, or None if absent.

    `<KEY>-investigation.md` -> `<KEY>-investigation-details.md`, next to it.
    """
    root, ext = os.path.splitext(report_path)
    candidate = f"{root}-details{ext}"
    return candidate if os.path.isfile(candidate) else None


def main():
    ap = argparse.ArgumentParser(description="Attach an investigation report")
    ap.add_argument("key", help="Jira epic key")
    ap.add_argument("--report", required=True, help="Path to the report markdown")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    meta, _ = read_frontmatter_validated(args.report, "investigation-report")

    # Wrong-epic guard: the report knows which epic it is for. A typo'd CI
    # variable must not attach this report onto a different epic.
    report_key = meta.get("jira_key") or meta.get("epic_id")
    if report_key and report_key != args.key:
        print(f"ERROR: report is for {report_key!r} but --key is {args.key!r}; "
              f"refusing to attach to the wrong epic.", file=sys.stderr)
        sys.exit(2)

    status = meta["status"]
    if status == "in_progress":
        print("ERROR: report status is still 'in_progress'; not publishing.",
              file=sys.stderr)
        sys.exit(2)

    # Completeness guard: a 'complete' report must actually cover every question.
    # This catches a dropped question (a dead investigate agent) being published
    # as if the run finished cleanly.
    total = meta.get("questions_total", 0)
    resolved = meta.get("questions_resolved", 0)
    if resolved > total:
        print(f"ERROR: questions_resolved ({resolved}) exceeds questions_total "
              f"({total}); report is inconsistent.", file=sys.stderr)
        sys.exit(2)
    if status == "complete" and (total <= 0 or resolved != total):
        print(f"ERROR: status=complete but resolved {resolved} of {total} "
              f"questions; incomplete runs must be published as 'error'/'blocked', "
              f"not 'complete'.", file=sys.stderr)
        sys.exit(2)

    with open(args.report, encoding="utf-8") as fh:
        content = fh.read()

    details_path = _details_path(args.report)
    details_content = None
    if details_path:
        with open(details_path, encoding="utf-8") as fh:
            details_content = fh.read()

    label = STATUS_LABELS.get(status)
    attach_names = WELL_KNOWN_NAME + (
        f", {DETAILS_WELL_KNOWN_NAME}" if details_content else "")
    print(f"epic={args.key} status={status} "
          f"recommendation={meta.get('recommendation')} label={label} "
          f"attach_as={attach_names}")
    if args.dry_run:
        return

    server, user, token = jira_utils.require_env()
    # Upload the new copy FIRST, then delete prior copies — so a failure here
    # (auth blip, rotated token) can never leave the epic with no report. Track
    # the ids we just created so we don't delete them in the cleanup below.
    new_ids = set()
    created = jira_utils.add_attachment(server, user, token, args.key,
                                        WELL_KNOWN_NAME, content)
    new_ids |= {a["id"] for a in (created or []) if "id" in a}
    if details_content:
        created_d = jira_utils.add_attachment(server, user, token, args.key,
                                              DETAILS_WELL_KNOWN_NAME,
                                              details_content)
        new_ids |= {a["id"] for a in (created_d or []) if "id" in a}
    # Only now that the new upload(s) succeeded, remove the prior copies.
    _delete_existing(server, user, token, args.key,
                     {WELL_KNOWN_NAME, DETAILS_WELL_KNOWN_NAME},
                     exclude_ids=new_ids)
    if label:
        # Clear any stale status label from a prior run, then apply the current.
        jira_utils.remove_labels(server, user, token, args.key,
                                 list(ALL_LABELS - {label}))
        jira_utils.add_labels(server, user, token, args.key, [label])
    print(f"OK: attached {attach_names} to {args.key}")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
