from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from artifact_utils import write_frontmatter  # noqa: E402


def _write_report(path, findings, run_started):
    path.write_text("# Report\n", encoding="utf-8")
    write_frontmatter(path, {
        "epic_id": "RHAI-1",
        "title": "Example",
        "parent_strat": "RHAISTRAT-1",
        "jira_key": "RHAI-1",
        "status": "complete",
        "recommendation": "go",
        "questions_total": 1,
        "questions_resolved": 1,
        "findings": findings,
        "run_started": run_started,
    }, "investigation-report")


def _dry_run(report):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "attach_report.py"), "RHAI-1",
         "--report", str(report), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_report_requires_findings_rollup(tmp_path):
    report = tmp_path / "report.md"
    _write_report(report, [], "2026-08-31T12:00:00Z")

    result = _dry_run(report)

    assert result.returncode == 2
    assert "findings rollup has 0 entries" in result.stderr


def test_complete_report_requires_run_started(tmp_path):
    report = tmp_path / "report.md"
    _write_report(report, [{"question": "Q01"}], None)

    result = _dry_run(report)

    assert result.returncode == 2
    assert "run_started is missing" in result.stderr
