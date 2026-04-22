"""Tests for count-trajectory-entries.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "count-trajectory-entries.py")


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _run(trajectory_file, audience_filter=""):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--trajectory-file", trajectory_file,
         "--audience-filter", audience_filter],
        capture_output=True, text=True,
    )


def _counts(result):
    """Parse '<matching> <legacy>' stdout into a tuple of ints."""
    assert result.returncode == 0, result.stderr
    parts = result.stdout.strip().split()
    return int(parts[0]), int(parts[1])


def _entry(audience_filter=None, **extra):
    """Build a trajectory entry. Pass audience_filter=None to omit the field."""
    e = {"wave": 1, "findings": {"new": 0}}
    e.update(extra)
    if audience_filter is not None:
        e["audience_filter"] = audience_filter
    return e


class TestCountTrajectoryEntries:
    """Counting matching and legacy trajectory entries."""

    def test_missing_trajectory_file(self):
        """Non-existent trajectory file → 0 0."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            assert _counts(_run(tf)) == (0, 0)

    def test_empty_trajectory(self):
        """Empty trajectory list → 0 0."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [])
            assert _counts(_run(tf)) == (0, 0)

    def test_only_legacy_entries(self):
        """Only entries without audience_filter → 0 matching, N legacy."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [_entry(), _entry(), _entry()])
            assert _counts(_run(tf, "devops")) == (0, 3)
            # Unfiltered current also doesn't promote legacy entries
            assert _counts(_run(tf, "")) == (0, 3)

    def test_filtered_exact_match(self):
        """Filtered current matches only entries with the same sorted list."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [
                _entry(audience_filter=["devops"]),
                _entry(audience_filter=["devops"]),
                _entry(audience_filter=["devops", "end-users"]),
                _entry(audience_filter=["end-users"]),
                _entry(audience_filter=[]),  # tagged as unfiltered
            ])
            assert _counts(_run(tf, "devops")) == (2, 0)

    def test_filtered_does_not_match_unfiltered_entry(self):
        """A filtered current must not match a tagged-unfiltered entry."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [_entry(audience_filter=[])])
            assert _counts(_run(tf, "devops")) == (0, 0)

    def test_unfiltered_matches_all_tagged(self):
        """Unfiltered current matches every tagged entry regardless of filter."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [
                _entry(audience_filter=["devops"]),
                _entry(audience_filter=["end-users"]),
                _entry(audience_filter=["devops", "end-users"]),
                _entry(audience_filter=[]),
                _entry(),  # legacy
            ])
            assert _counts(_run(tf, "")) == (4, 1)

    def test_multi_filter_match(self):
        """Multi-audience filter requires sorted-list equality."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [
                _entry(audience_filter=["devops", "end-users"]),
                _entry(audience_filter=["devops"]),
            ])
            # Whitespace + ordering tolerance: 'end-users, devops' normalizes to ['devops','end-users']
            assert _counts(_run(tf, "end-users, devops")) == (1, 0)

    def test_mixed_legacy_and_tagged(self):
        """Mixed trajectory: counts legacy and matching independently."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [
                _entry(),                                   # legacy
                _entry(audience_filter=["devops"]),         # match for 'devops'
                _entry(audience_filter=["end-users"]),      # not a match for 'devops'
                _entry(),                                   # legacy
                _entry(audience_filter=["devops"]),         # match for 'devops'
            ])
            assert _counts(_run(tf, "devops")) == (2, 2)
