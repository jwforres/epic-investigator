#!/usr/bin/env python3
"""Fetch an Investigation epic into the working area for investigation.

Two input paths:

    # CI path — fetch the epic from Jira by key
    python3 scripts/fetch_epic.py RHAISTRAT-1234-E001 [--parent-strat RHAISTRAT-1234]

    # Local-dev path — ingest an epic-task markdown file produced by epic-creator
    python3 scripts/fetch_epic.py --from-file ../epic-creator/artifacts/epic-tasks/RHAISTRAT-1234-E001.md

Either way the epic is written to <artifacts-dir>/investigations/<KEY>-input.md
(default `artifacts/investigations/`) with epic-task frontmatter and the
description body (Scope / questions / acceptance criteria) preserved. The
investigate skill reads that body.

Only epics of type Investigation are accepted — Implementation epics are
rejected so CI doesn't waste a run.
"""

import argparse
import os
import re
import sys

import yaml

from artifact_utils import (
    read_frontmatter_validated,
    write_frontmatter,
    ValidationError,
)
import jira_utils

DEFAULT_ARTIFACTS_DIR = "artifacts"
INVESTIGATIONS_SUBDIR = "investigations"
_STRAT_RE = re.compile(r"RHAISTRAT-\d+")


def _blocked_keys(issue):
    """Jira keys reached by outward ``blocks`` links, in Jira order."""
    keys = []
    for link in (issue.get("fields") or {}).get("issuelinks") or []:
        outward = link.get("outwardIssue")
        if outward and (link.get("type") or {}).get("outward") == "blocks":
            keys.append(outward["key"])
    return keys


def _attached_frontmatter(server, user, token, issue):
    """Return epic-creator's attached frontmatter, or None when unavailable."""
    for attachment in (issue.get("fields") or {}).get("attachment") or []:
        if not str(attachment.get("filename", "")).endswith("-frontmatter.yaml"):
            continue
        try:
            content = jira_utils.download_attachment(
                attachment["content"], user, token, server=server
            )
            parsed = yaml.safe_load(content) or {}
        except (KeyError, OSError, ValueError, yaml.YAMLError) as exc:
            print(
                f"WARNING: could not read {issue.get('key')} frontmatter: {exc}",
                file=sys.stderr,
            )
            return None
        if isinstance(parsed, dict):
            return parsed
        print(
            f"WARNING: {issue.get('key')} frontmatter is not a mapping",
            file=sys.stderr,
        )
        return None
    return None


def _gate_ids(frontmatter):
    """Normalize epic-creator's comma-separated ``gated_by`` value."""
    if not frontmatter:
        return []
    value = frontmatter.get("gated_by")
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _resolve_gated_epics(server, user, token, issue, gating_id):
    """Resolve membership from Jira links and retain advisory sibling context."""
    keys = _blocked_keys(issue)
    context = []
    if not keys:
        print(
            f"WARNING: {issue.get('key')} has no outward blocks links; "
            "gated_epics will be empty",
            file=sys.stderr,
        )
        return [], []

    for key in keys:
        try:
            sibling = jira_utils.get_issue(
                server, user, token, key,
                fields=["summary", "description", "attachment"]
            )
        except Exception as exc:  # noqa: BLE001 - advisory lookup must not abort the fetch
            print(
                f"WARNING: could not fetch {key} gated_by metadata: {exc}; "
                "using the Jira blocks relationship",
                file=sys.stderr,
            )
            context.append({"jira_key": key, "context_unavailable": True})
            continue
        fields = sibling.get("fields") or {}
        sibling_frontmatter = _attached_frontmatter(server, user, token, sibling)
        entry = {
            "jira_key": key,
            "summary": fields.get("summary") or key,
            "description": jira_utils.adf_to_markdown(fields.get("description"))
            if fields.get("description")
            else "",
        }
        if sibling_frontmatter is None:
            print(
                f"WARNING: {key} is blocked by {issue.get('key')}, but its "
                "gated_by metadata is unavailable; using the Jira blocks relationship",
                file=sys.stderr,
            )
        else:
            gates = _gate_ids(sibling_frontmatter)
            entry["gated_by"] = gates
            if sibling_frontmatter.get("gate_failure_impact") is not None:
                entry["gate_failure_impact"] = sibling_frontmatter["gate_failure_impact"]
            if gating_id and gating_id not in gates:
                print(
                    f"WARNING: {key} is blocked by {issue.get('key')}, but gated_by "
                    f"does not contain {gating_id}; using the Jira blocks relationship",
                    file=sys.stderr,
                )
        context.append(entry)
    return keys, context


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
                "priority", "components", "issuelinks", "attachment"])
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

    frontmatter = _attached_frontmatter(server, user, token, issue)
    gating_id = (frontmatter or {}).get("epic_id")
    if not gating_id:
        print(
            f"WARNING: {key} has no epic-creator epic_id; sibling gated_by "
            "metadata cannot be cross-checked",
            file=sys.stderr,
        )
    gated_epics, gated_epic_context = _resolve_gated_epics(
        server, user, token, issue, str(gating_id) if gating_id else None
    )

    meta = {
        "epic_id": key,
        "title": f.get("summary", key),
        "parent_strat": parent_strat,
        "jira_key": key,
        "component": component,
        "team": "unknown",
        "type": "Investigation",
        "priority": priority,
        "gating_id": gating_id,
        "gated_epics": gated_epics,
        "gated_epic_context": gated_epic_context,
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
            "team", "type", "priority", "gating_id", "gated_epics",
            "gated_epic_context")
    return {k: meta[k] for k in keep if k in meta}, body


def main():
    ap = argparse.ArgumentParser(description="Fetch an Investigation epic")
    ap.add_argument("key", nargs="?", help="Jira epic key, e.g. RHAISTRAT-1234-E001")
    ap.add_argument("--from-file", help="Ingest a local epic-task markdown file")
    ap.add_argument("--parent-strat", help="Override parent strategy (RHAISTRAT-NNNN)")
    ap.add_argument("--artifacts-dir", default=DEFAULT_ARTIFACTS_DIR,
                    help="Artifacts root; input is written to "
                    "<artifacts-dir>/investigations/ (default: artifacts)")
    args = ap.parse_args()

    out_dir = os.path.join(args.artifacts_dir, INVESTIGATIONS_SUBDIR)

    if args.from_file:
        meta, body = _ingest_file(args.from_file)
    elif args.key:
        meta, body = _fetch_from_jira(args.key, args.parent_strat)
    else:
        ap.error("provide an epic key or --from-file")

    if meta.get("type") != "Investigation":
        meta["type"] = "Investigation"

    out_path = os.path.join(out_dir, f"{meta['epic_id']}-input.md")
    os.makedirs(out_dir, exist_ok=True)
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
