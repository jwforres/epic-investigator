import importlib.util
from pathlib import Path
import sys

import pytest
SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "finalize_report", SCRIPTS / "finalize_report.py")
finalize_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finalize_report)

from artifact_utils import read_frontmatter, write_frontmatter  # noqa: E402


def _report(path, resolved=2):
    path.write_text("# Report\n", encoding="utf-8")
    write_frontmatter(path, {
        "epic_id": "RHAI-1",
        "title": "Example",
        "parent_strat": "RHAISTRAT-1",
        "jira_key": "RHAI-1",
        "status": "complete",
        "recommendation": "go",
        "questions_total": 2,
        "questions_resolved": resolved,
    }, "investigation-report")


def _finding(path, number, tier, answer, confidence):
    path.write_text(
        f"## Q{number:02d}: Question {number}\n\n"
        f"- **Tiers executed:** {tier}\n"
        f"- **Answer:** {answer}\n"
        f"- **Confidence:** {confidence}\n",
        encoding="utf-8",
    )


def test_finalize_stamps_sorted_findings_and_start_time(tmp_path):
    report = tmp_path / "report.md"
    state = tmp_path / "state.yaml"
    _report(report)
    _finding(tmp_path / "q02.md", 2, "desk | deferred", "PARTIAL", "medium")
    _finding(tmp_path / "q01.md", 1, "desk", "YES", "high")
    state.write_text("started: '2026-08-31T12:00:00Z'\n", encoding="utf-8")

    finalize_report.finalize(report, str(tmp_path / "q*.md"), state)

    meta, _ = read_frontmatter(report)
    assert meta["run_started"] == "2026-08-31T12:00:00Z"
    assert meta["findings"] == [
        {"question": "Q01", "tier": "desk", "answer": "YES",
         "confidence": "high"},
        {"question": "Q02", "tier": "desk | deferred", "answer": "PARTIAL",
         "confidence": "medium"},
    ]


def test_finalize_rejects_malformed_finding(tmp_path):
    report = tmp_path / "report.md"
    state = tmp_path / "state.yaml"
    _report(report)
    (tmp_path / "q01.md").write_text("## Q01: Missing fields\n", encoding="utf-8")
    state.write_text("started: now\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing tier, answer, confidence"):
        finalize_report.finalize(report, str(tmp_path / "q*.md"), state)


def test_finalize_rejects_incomplete_rollup(tmp_path):
    report = tmp_path / "report.md"
    state = tmp_path / "state.yaml"
    _report(report)
    _finding(tmp_path / "q01.md", 1, "desk", "YES", "high")
    state.write_text("started: now\n", encoding="utf-8")

    with pytest.raises(ValueError, match="2 resolved.*1 finding"):
        finalize_report.finalize(report, str(tmp_path / "q*.md"), state)
