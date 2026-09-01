"""Tests for deterministic gated-epic discovery."""

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("fetch_epic", SCRIPTS / "fetch_epic.py")
fetch_epic = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fetch_epic)


def _investigation(*keys):
    return {
        "key": "RHAI-28",
        "fields": {
            "issuelinks": [
                {
                    "type": {"outward": "blocks", "inward": "is blocked by"},
                    "outwardIssue": {"key": key},
                }
                for key in keys
            ]
        },
    }


def test_only_outward_blocks_links_define_membership():
    issue = _investigation("RHAI-30")
    issue["fields"]["issuelinks"].extend(
        [
            {
                "type": {"outward": "relates to"},
                "outwardIssue": {"key": "RHAI-31"},
            },
            {
                "type": {"outward": "blocks", "inward": "is blocked by"},
                "inwardIssue": {"key": "RHAI-32"},
            },
        ]
    )

    assert fetch_epic._blocked_keys(issue) == ["RHAI-30"]


def test_frontmatter_disagreement_warns_but_blocks_link_wins(monkeypatch, capsys):
    monkeypatch.setattr(
        fetch_epic.jira_utils,
        "get_issue",
        lambda *args, **kwargs: {"key": "RHAI-30", "fields": {}},
    )
    monkeypatch.setattr(
        fetch_epic,
        "_attached_frontmatter",
        lambda *args: {"gated_by": "RHAISTRAT-1586-E002"},
    )

    resolved = fetch_epic._resolve_gated_epics(
        "https://jira.example",
        "user",
        "token",
        _investigation("RHAI-30"),
        "RHAISTRAT-1586-E001",
    )

    assert resolved[0] == ["RHAI-30"]
    assert "using the Jira blocks relationship" in capsys.readouterr().err


def test_missing_sibling_frontmatter_warns_but_blocks_link_wins(monkeypatch, capsys):
    monkeypatch.setattr(
        fetch_epic.jira_utils,
        "get_issue",
        lambda *args, **kwargs: {"key": "RHAI-30", "fields": {}},
    )
    monkeypatch.setattr(fetch_epic, "_attached_frontmatter", lambda *args: None)

    resolved = fetch_epic._resolve_gated_epics(
        "https://jira.example",
        "user",
        "token",
        _investigation("RHAI-30"),
        "RHAISTRAT-1586-E001",
    )

    assert resolved[0] == ["RHAI-30"]
    assert "metadata is unavailable" in capsys.readouterr().err


def test_sibling_fetch_failure_warns_but_blocks_link_wins(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("temporary Jira failure")

    monkeypatch.setattr(fetch_epic.jira_utils, "get_issue", fail)

    resolved = fetch_epic._resolve_gated_epics(
        "https://jira.example",
        "user",
        "token",
        _investigation("RHAI-30"),
        "RHAISTRAT-1586-E001",
    )

    assert resolved == (
        ["RHAI-30"],
        [{"jira_key": "RHAI-30", "context_unavailable": True}],
    )
    assert "using the Jira blocks relationship" in capsys.readouterr().err


def test_no_blocks_links_is_empty_and_nonfatal(capsys):
    resolved = fetch_epic._resolve_gated_epics(
        "https://jira.example",
        "user",
        "token",
        _investigation(),
        "RHAISTRAT-1586-E001",
    )

    assert resolved == ([], [])
    assert "gated_epics will be empty" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RHAISTRAT-1-E001,RHAISTRAT-1-E002", ["RHAISTRAT-1-E001", "RHAISTRAT-1-E002"]),
        (["RHAISTRAT-1-E001", "RHAISTRAT-1-E002"], ["RHAISTRAT-1-E001", "RHAISTRAT-1-E002"]),
        (None, []),
    ],
)
def test_gate_ids_accepts_serialized_and_native_lists(raw, expected):
    assert fetch_epic._gate_ids({"gated_by": raw}) == expected


def test_sibling_context_reuses_the_gate_validation_fetch(monkeypatch):
    calls = []

    def get_issue(*args, **kwargs):
        calls.append(kwargs["fields"])
        return {
            "key": "RHAI-34",
            "fields": {
                "summary": "Validate the Python SDK",
                "description": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Exercise tracing."}],
                        }
                    ],
                },
            },
        }

    monkeypatch.setattr(fetch_epic.jira_utils, "get_issue", get_issue)
    monkeypatch.setattr(
        fetch_epic,
        "_attached_frontmatter",
        lambda *args: {
            "gated_by": "RHAISTRAT-1586-E001",
            "gate_failure_impact": {"action": "rewrite"},
        },
    )

    keys, context = fetch_epic._resolve_gated_epics(
        "https://jira.example",
        "user",
        "token",
        _investigation("RHAI-34"),
        "RHAISTRAT-1586-E001",
    )

    assert keys == ["RHAI-34"]
    assert len(calls) == 1
    assert calls[0] == ["summary", "description", "attachment"]
    assert context == [
        {
            "jira_key": "RHAI-34",
            "summary": "Validate the Python SDK",
            "description": "Exercise tracing.\n\n",
            "gated_by": ["RHAISTRAT-1586-E001"],
            "gate_failure_impact": {"action": "rewrite"},
        }
    ]
