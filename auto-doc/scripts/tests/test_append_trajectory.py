"""Tests for append-trajectory.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "append-trajectory.py")


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run(trajectory_file, wave_summary):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--trajectory-file", trajectory_file,
         "--wave-summary", wave_summary],
        capture_output=True, text=True,
    )


class TestAppendTrajectory:
    """Core append behavior."""

    def test_creates_trajectory_from_scratch(self):
        """Appends to non-existent trajectory file (creates it)."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            ws = os.path.join(td, "wave-summary.json")
            _write_json(ws, {"wave": 1, "findings": {"new": 5}})

            result = _run(tf, ws)
            assert result.returncode == 0

            trajectory = _read_json(tf)
            assert len(trajectory) == 1
            assert trajectory[0]["wave"] == 1

    def test_appends_to_existing(self):
        """Appends wave 2 summary to trajectory with wave 1."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [{"wave": 1, "findings": {"new": 10}}])

            ws = os.path.join(td, "wave-summary.json")
            _write_json(ws, {"wave": 2, "findings": {"new": 3}})

            result = _run(tf, ws)
            assert result.returncode == 0

            trajectory = _read_json(tf)
            assert len(trajectory) == 2
            assert trajectory[0]["wave"] == 1
            assert trajectory[1]["wave"] == 2

    def test_empty_summary_skipped(self):
        """Empty wave summary file → trajectory unchanged."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [{"wave": 1}])

            ws = os.path.join(td, "wave-summary.json")
            _write_json(ws, {})

            result = _run(tf, ws)
            assert result.returncode == 0
            assert "Warning: empty wave summary" in result.stderr

            trajectory = _read_json(tf)
            assert len(trajectory) == 1

    def test_missing_summary_file(self):
        """Missing wave summary file → trajectory unchanged."""
        with tempfile.TemporaryDirectory() as td:
            tf = os.path.join(td, "trajectory.json")
            _write_json(tf, [])

            ws = os.path.join(td, "nonexistent.json")

            result = _run(tf, ws)
            assert result.returncode == 0

            trajectory = _read_json(tf)
            assert len(trajectory) == 0
