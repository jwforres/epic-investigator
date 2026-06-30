#!/usr/bin/env python3
"""Fetch an Investigation epic into the working area for investigation.

Two input paths:

    # CI path — fetch the epic from Jira by key
    python3 scripts/fetch_epic.py RHAISTRAT-1234-E001 [--parent-strat RHAISTRAT-1234]

    # Local-dev path — ingest an epic-task markdown file produced by epic-creator
    python3 scripts/fetch_epic.py --from-file ../epic-creator/artifacts/epic-tasks/RHAISTRAT-1234-E001.md

Either way the epic is written to artifacts/investigations/<KEY>-input.md with
epic-task frontmatter and the description body (Scope / questions / acceptance
criteria) preserved. The investigate skill reads that body.

Only epics of type Investigation are accepted — Implementation epics are
rejected so CI doesn't waste a run.
"""

import argparse
import os
import re
import sys

from artifact_utils import (
    read_frontmatter_validated,
    write_frontmatter,
    ValidationError,
)
import jira_utils

OUT_DIR = "artifacts/investigations"
_STRAT_RE = re.compile(r"RHAISTRAT-\d+")


def _derive_parent_strat(issue_fields, override):
    """Best-effort parent strategy: explicit override, then labels, then parent."""
    if override:
        return override
    for label in issue_fields.get("labels", []) or []:
        m = _STRAT_RE.search(label)
        if m:
            return m.group(0)
    parent = issue_fields.get("parent") or {}
    key = parent.get("key", "")
    if _STRAT_RE.fullmatch(key):
        return key
    return None


def _fetch_from_jira(key, parent_override):
    server, user, token = jira_utils.require_env()
    issue = jira_utils.get_issue(
        server, user, token, key,
        fields=["summary", "description", "labels", "parent",
                "priority", "components"])
    f = issue.get("fields", {})

    parent_strat = _derive_parent_strat(f, parent_override)
    if not parent_strat:
        print(f"ERROR: could not determine parent strategy for {key}. "
              f"Pass --parent-strat RHAISTRAT-NNNN.", file=sys.stderr)
        sys.exit(2)

    components = f.get("components") or []
    component = components[0]["name"] if components else "unknown"
    priority_name = (f.get("priority") or {}).get("name", "")
    priority = priority_name if priority_name in ("P0", "P1", "P2") else "P1"

    body = jira_utils.adf_to_markdown(f.get("description")) \
        if f.get("description") else ""

    meta = {
        "epic_id": key,
        "title": f.get("summary", key),
        "parent_strat": parent_strat,
        "jira_key": key,
        "component": component,
        "team": "unknown",
        "type": "Investigation",
        "priority": priority,
    }
    return meta, body


def _ingest_file(path):
    """Read an epic-task file from epic-creator and re-emit as input."""
    meta, body = read_frontmatter_validated(path, "epic-task")
    if meta.get("type") != "Investigation":
        print(f"ERROR: {path} is type '{meta.get('type')}', not Investigation.",
              file=sys.stderr)
        sys.exit(2)
    # Keep only the epic-task fields we re-validate against on write.
    keep = ("epic_id", "title", "parent_strat", "jira_key", "component",
            "team", "type", "priority")
    return {k: meta[k] for k in keep if k in meta}, body


def main():
    ap = argparse.ArgumentParser(description="Fetch an Investigation epic")
    ap.add_argument("key", nargs="?", help="Jira epic key, e.g. RHAISTRAT-1234-E001")
    ap.add_argument("--from-file", help="Ingest a local epic-task markdown file")
    ap.add_argument("--parent-strat", help="Override parent strategy (RHAISTRAT-NNNN)")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()

    if args.from_file:
        meta, body = _ingest_file(args.from_file)
    elif args.key:
        meta, body = _fetch_from_jira(args.key, args.parent_strat)
    else:
        ap.error("provide an epic key or --from-file")

    if meta.get("type") != "Investigation":
        meta["type"] = "Investigation"

    out_path = os.path.join(args.out_dir, f"{meta['epic_id']}-input.md")
    os.makedirs(args.out_dir, exist_ok=True)
    # Seed the file with the raw body (no frontmatter delimiters); a file with
    # no frontmatter is read as all-body, so write_frontmatter then prepends the
    # validated frontmatter while preserving the body intact.
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    write_frontmatter(out_path, meta, "epic-task")
    print(out_path)


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
