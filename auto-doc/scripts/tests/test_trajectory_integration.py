"""End-to-end test for the trajectory pipeline glue.

Chains aggregate-wave-summaries.py → append-trajectory.py →
count-trajectory-entries.py with a multi-filter fixture, then asserts
counts match the asymmetric scoping rule. Catches regressions in the
glue between the three scripts that unit tests on each script in
isolation would miss.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
AGGREGATE = os.path.join(SCRIPTS_DIR, "aggregate-wave-summaries.py")
APPEND = os.path.join(SCRIPTS_DIR, "append-trajectory.py")
COUNT = os.path.join(SCRIPTS_DIR, "count-trajectory-entries.py")


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _summary(new=1):
    return {
        "wave": 2,
        "findings": {"new": new, "by_check": {}, "by_suggestion_category": {}},
        "dismissals": {"total": 0, "by_tier": {}},
        "uncleared_remaining": 0,
        "entities_resolved_this_wave": 0,
    }


def _aggregate(td, name, audience_filter):
    """Run aggregate, return path to the resulting aggregate file."""
    summary_path = os.path.join(td, f"in-{name}.json")
    _write_json(summary_path, _summary())
    out_path = os.path.join(td, f"agg-{name}.json")
    result = subprocess.run(
        [sys.executable, AGGREGATE,
         "--summaries", summary_path,
         "--output", out_path,
         "--audience-filter", audience_filter],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_path


def _append(trajectory_file, agg_path):
    result = subprocess.run(
        [sys.executable, APPEND,
         "--trajectory-file", trajectory_file,
         "--wave-summary", agg_path],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def _count(trajectory_file, audience_filter):
    result = subprocess.run(
        [sys.executable, COUNT,
         "--trajectory-file", trajectory_file,
         "--audience-filter", audience_filter],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    parts = result.stdout.strip().split()
    return int(parts[0]), int(parts[1])


class TestTrajectoryPipelineIntegration:
    """Aggregate → append → count, end to end."""

    def test_full_pipeline_with_legacy_and_tagged_entries(self):
        """Build a trajectory with one legacy + two tagged entries, then count."""
        with tempfile.TemporaryDirectory() as td:
            trajectory = os.path.join(td, "trajectory.json")

            # Seed a legacy (untagged) entry — simulates an existing project.
            _write_json(trajectory, [_summary(new=99)])

            # Run the real pipeline twice with different filters.
            agg_devops = _aggregate(td, "devops", "devops")
            _append(trajectory, agg_devops)

            agg_end_users = _aggregate(td, "end-users", "end-users")
            _append(trajectory, agg_end_users)

            # Sanity-check the persisted file shape.
            entries = _read_json(trajectory)
            assert len(entries) == 3
            assert "audience_filter" not in entries[0]      # legacy
            assert entries[1]["audience_filter"] == ["devops"]
            assert entries[2]["audience_filter"] == ["end-users"]

            # Count under different current filters.
            assert _count(trajectory, "") == (2, 1)              # unfiltered: all tagged
            assert _count(trajectory, "devops") == (1, 1)        # exact-match only
            assert _count(trajectory, "end-users") == (1, 1)
            assert _count(trajectory, "agents") == (0, 1)        # no tagged matches
            assert _count(trajectory, "devops,end-users") == (0, 1)  # composite, no match
