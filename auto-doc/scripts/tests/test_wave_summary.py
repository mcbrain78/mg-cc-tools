"""Tests for wave-summary.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "wave-summary.py")


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _make_finding(section="monitoring", check="dangling-prose-reference",
                  description="test", suggestion="Likely a database table"):
    return {
        "document": "OPERATIONS",
        "section": section,
        "audience": "devops",
        "check": check,
        "description": description,
        "suggestion": suggestion,
    }


def _run(findings_file, prev_findings_file, uncleared_file,
         dismissed_file, wave, output):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--findings-file", findings_file,
         "--prev-findings-file", prev_findings_file,
         "--uncleared-file", uncleared_file,
         "--dismissed-file", dismissed_file,
         "--wave", str(wave),
         "--output", output],
        capture_output=True, text=True,
    )


class TestWaveSummaryBasic:
    """Core wave summary generation."""

    def test_empty_wave(self):
        """No new findings, no dismissals → zero counts."""
        with tempfile.TemporaryDirectory() as td:
            ff = os.path.join(td, "findings.json")
            pf = os.path.join(td, "prev.json")
            uf = os.path.join(td, "uncleared.json")
            df = os.path.join(td, "dismissed.json")
            out = os.path.join(td, "summary.json")

            _write_json(ff, [])
            _write_json(pf, [])
            _write_json(uf, [])
            _write_json(df, [])

            result = _run(ff, pf, uf, df, 1, out)
            assert result.returncode == 0

            summary = _read_json(out)
            assert summary["wave"] == 1
            assert summary["findings"]["new"] == 0
            assert summary["dismissals"]["total"] == 0
            assert summary["uncleared_remaining"] == 0

    def test_new_findings_counted(self):
        """New findings (in current but not prev) are counted."""
        with tempfile.TemporaryDirectory() as td:
            f1 = _make_finding(description="old finding")
            f2 = _make_finding(section="deployment", description="new finding",
                               suggestion="Likely a function name")

            ff = os.path.join(td, "findings.json")
            pf = os.path.join(td, "prev.json")
            uf = os.path.join(td, "uncleared.json")
            df = os.path.join(td, "dismissed.json")
            out = os.path.join(td, "summary.json")

            _write_json(ff, [f1, f2])
            _write_json(pf, [f1])
            _write_json(uf, [{"name": "x", "section": "s"}])
            _write_json(df, [])

            result = _run(ff, pf, uf, df, 2, out)
            assert result.returncode == 0

            summary = _read_json(out)
            assert summary["findings"]["new"] == 1
            assert summary["uncleared_remaining"] == 1

    def test_by_check_breakdown(self):
        """Findings grouped by check type."""
        with tempfile.TemporaryDirectory() as td:
            findings = [
                _make_finding(check="dangling-prose-reference", description="d1"),
                _make_finding(check="dangling-prose-reference", description="d2"),
                _make_finding(check="internal-contradiction", description="d3"),
            ]

            ff = os.path.join(td, "findings.json")
            pf = os.path.join(td, "prev.json")
            uf = os.path.join(td, "uncleared.json")
            df = os.path.join(td, "dismissed.json")
            out = os.path.join(td, "summary.json")

            _write_json(ff, findings)
            _write_json(pf, [])
            _write_json(uf, [])
            _write_json(df, [])

            result = _run(ff, pf, uf, df, 1, out)
            assert result.returncode == 0

            summary = _read_json(out)
            assert summary["findings"]["by_check"]["dangling-prose-reference"] == 2
            assert summary["findings"]["by_check"]["internal-contradiction"] == 1


class TestWaveSummarySuggestionClassification:
    """Suggestion text classified into broad categories."""

    def test_db_suggestion(self):
        with tempfile.TemporaryDirectory() as td:
            ff = os.path.join(td, "findings.json")
            pf = os.path.join(td, "prev.json")
            uf = os.path.join(td, "uncleared.json")
            df = os.path.join(td, "dismissed.json")
            out = os.path.join(td, "summary.json")

            _write_json(ff, [_make_finding(suggestion="Likely a database table")])
            _write_json(pf, [])
            _write_json(uf, [])
            _write_json(df, [])

            _run(ff, pf, uf, df, 1, out)
            summary = _read_json(out)
            assert "missing_db_ref" in summary["findings"]["by_suggestion_category"]

    def test_code_suggestion(self):
        with tempfile.TemporaryDirectory() as td:
            ff = os.path.join(td, "findings.json")
            pf = os.path.join(td, "prev.json")
            uf = os.path.join(td, "uncleared.json")
            df = os.path.join(td, "dismissed.json")
            out = os.path.join(td, "summary.json")

            _write_json(ff, [_make_finding(suggestion="Appears to be a function name")])
            _write_json(pf, [])
            _write_json(uf, [])
            _write_json(df, [])

            _run(ff, pf, uf, df, 1, out)
            summary = _read_json(out)
            assert "missing_code_ref" in summary["findings"]["by_suggestion_category"]


class TestWaveSummaryDismissals:
    """Dismissal tier classification."""

    def test_dismissals_counted(self):
        with tempfile.TemporaryDirectory() as td:
            ff = os.path.join(td, "findings.json")
            pf = os.path.join(td, "prev.json")
            uf = os.path.join(td, "uncleared.json")
            df = os.path.join(td, "dismissed.json")
            out = os.path.join(td, "summary.json")

            _write_json(ff, [])
            _write_json(pf, [])
            _write_json(uf, [])
            _write_json(df, [
                {"name": "bash", "reason": "Universal builtin"},
                {"name": "http://example.com", "reason": "No constructible ref type for URLs"},
                {"name": "status", "reason": "Contextual: used as plain English"},
            ])

            result = _run(ff, pf, uf, df, 1, out)
            assert result.returncode == 0

            summary = _read_json(out)
            assert summary["dismissals"]["total"] == 3
            tiers = summary["dismissals"]["by_tier"]
            assert tiers.get("universal", 0) >= 1
            assert tiers.get("no_ref_type", 0) >= 1
            assert tiers.get("contextual", 0) >= 1
