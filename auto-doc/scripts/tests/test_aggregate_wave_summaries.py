"""Tests for aggregate-wave-summaries.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "aggregate-wave-summaries.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _make_summary(wave=1, new=5, by_check=None, by_suggestion=None,
                  dismissed=2, by_tier=None, uncleared=10, resolved=7):
    """Build a wave summary dict matching wave-summary.py output shape."""
    return {
        "wave": wave,
        "findings": {
            "new": new,
            "by_check": by_check or {},
            "by_suggestion_category": by_suggestion or {},
        },
        "dismissals": {
            "total": dismissed,
            "by_tier": by_tier or {},
        },
        "uncleared_remaining": uncleared,
        "entities_resolved_this_wave": resolved,
    }


class TestAggregate:
    """Aggregation of per-document wave summaries."""

    def test_single_summary_passthrough(self):
        """One document → aggregate equals the input."""
        with tempfile.TemporaryDirectory() as td:
            s1 = _make_summary(
                wave=2, new=3,
                by_check={"dangling-prose-reference": 3},
                by_suggestion={"missing_code_ref": 2, "cosmetic": 1},
                dismissed=1, by_tier={"universal": 1},
                uncleared=5, resolved=4,
            )
            p1 = _write_json(td, "s1.json", s1)
            out = os.path.join(td, "merged.json")

            result = subprocess.run(
                [sys.executable, SCRIPT, "--summaries", p1, "--output", out],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(out)
            assert merged["wave"] == 2
            assert merged["findings"]["new"] == 3
            assert merged["findings"]["by_check"]["dangling-prose-reference"] == 3
            assert merged["dismissals"]["total"] == 1
            assert merged["uncleared_remaining"] == 5

    def test_two_documents_merged(self):
        """Two documents → counts summed."""
        with tempfile.TemporaryDirectory() as td:
            s1 = _make_summary(
                wave=2, new=3,
                by_check={"dangling-prose-reference": 2, "internal-contradiction": 1},
                by_suggestion={"missing_code_ref": 2, "cosmetic": 1},
                dismissed=1, by_tier={"universal": 1},
                uncleared=5, resolved=4,
            )
            s2 = _make_summary(
                wave=2, new=2,
                by_check={"dangling-prose-reference": 2},
                by_suggestion={"missing_db_ref": 2},
                dismissed=3, by_tier={"universal": 1, "no_ref_type": 2},
                uncleared=8, resolved=5,
            )
            p1 = _write_json(td, "s1.json", s1)
            p2 = _write_json(td, "s2.json", s2)
            out = os.path.join(td, "merged.json")

            result = subprocess.run(
                [sys.executable, SCRIPT, "--summaries", p1, p2, "--output", out],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(out)
            assert merged["findings"]["new"] == 5
            assert merged["findings"]["by_check"]["dangling-prose-reference"] == 4
            assert merged["findings"]["by_check"]["internal-contradiction"] == 1
            assert merged["findings"]["by_suggestion_category"]["missing_code_ref"] == 2
            assert merged["findings"]["by_suggestion_category"]["missing_db_ref"] == 2
            assert merged["dismissals"]["total"] == 4
            assert merged["dismissals"]["by_tier"]["universal"] == 2
            assert merged["dismissals"]["by_tier"]["no_ref_type"] == 2
            assert merged["uncleared_remaining"] == 13
            assert merged["entities_resolved_this_wave"] == 9

    def test_three_documents(self):
        """Three documents (the real-world case) all contribute."""
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for i, new_count in enumerate([4, 2, 1]):
                s = _make_summary(wave=2, new=new_count, uncleared=i + 1)
                paths.append(_write_json(td, f"s{i}.json", s))
            out = os.path.join(td, "merged.json")

            result = subprocess.run(
                [sys.executable, SCRIPT, "--summaries", *paths, "--output", out],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(out)
            assert merged["findings"]["new"] == 7
            assert merged["uncleared_remaining"] == 6  # 1+2+3

    def test_missing_summary_file_skipped(self):
        """Non-existent file is silently skipped."""
        with tempfile.TemporaryDirectory() as td:
            s1 = _make_summary(wave=1, new=3)
            p1 = _write_json(td, "s1.json", s1)
            missing = os.path.join(td, "does-not-exist.json")
            out = os.path.join(td, "merged.json")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--summaries", p1, missing,
                 "--output", out],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(out)
            assert merged["findings"]["new"] == 3

    def test_stderr_reports_count(self):
        """Stderr shows how many summaries were aggregated."""
        with tempfile.TemporaryDirectory() as td:
            s1 = _make_summary()
            s2 = _make_summary()
            p1 = _write_json(td, "s1.json", s1)
            p2 = _write_json(td, "s2.json", s2)
            out = os.path.join(td, "merged.json")

            result = subprocess.run(
                [sys.executable, SCRIPT, "--summaries", p1, p2, "--output", out],
                capture_output=True, text=True,
            )
            assert "Aggregated 2 summaries" in result.stderr
