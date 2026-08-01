"""Shared fixtures for the resumable-workflow test suite.

The tool directory is ``resumable-workflow`` — not a valid Python identifier — so
spec's package-path import style (``from spec.scripts.improve_files import …``) is
unavailable here. We use the sys.path-insert pattern from
``permission-hooks/scripts/tests/test_usage_read.py`` instead, which works fine
under a hyphenated directory.

Every fixture is rooted at ``tmp_path``: pyproject sets ``-n auto`` (pytest-xdist),
so a shared on-disk fixture directory would race across workers.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, SCRIPTS_DIR)

import run_state  # noqa: E402


@pytest.fixture
def out(capsys):
    """Parse the JSON object a subcommand printed to stdout."""
    def _read():
        return json.loads(capsys.readouterr().out)
    return _read


@pytest.fixture
def run_dir(tmp_path):
    """A resolved run dir, ready for add/claim/complete."""
    d = tmp_path / "runs" / "run-test"
    assert run_state.main(["resolve", "--task", "test task", "--run-dir", str(d)]) == 0
    return d


@pytest.fixture
def question(run_dir, capsys):
    """A recorded question node; returns its id (which is also its step id)."""
    assert run_state.main(
        ["add", str(run_dir), "--kind", "question", "--text", "Where is auth checked?"]
    ) == 0
    return json.loads(capsys.readouterr().out)["id"]


@pytest.fixture
def write_payload(run_dir):
    """Write a payload that passes `complete`'s shape check."""
    def _write(step_id, body="A sufficiently long finding body for the floor.\n"):
        path = run_state._payload_path(run_dir, step_id)
        path.write_text(body, encoding="utf-8")
        return path
    return _write


@pytest.fixture
def do_claim(run_dir, capsys):
    """Claim a step and return the emitted JSON.

    Drains the capture buffer first so the result is this claim's output alone,
    whatever the test emitted beforehand."""
    def _claim(step_id, *extra):
        capsys.readouterr()
        assert run_state.main(
            ["claim", str(run_dir), "--step", step_id, *extra]
        ) == 0
        return json.loads(capsys.readouterr().out)
    return _claim
