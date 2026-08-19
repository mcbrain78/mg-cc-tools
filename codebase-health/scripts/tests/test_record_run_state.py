"""Tests for record-run-state.py."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "record-run-state.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_set_checkpoint_writes_in_progress(tmp_path):
    s = tmp_path / "state.json"
    r = run("set-checkpoint", "--state", str(s), "--category", "orphaned-code",
            "--checkpoint", "abc1234")
    assert r.returncode == 0, r.stderr
    d = json.loads(s.read_text())
    assert d == {
        "status": "in_progress",
        "category": "orphaned-code",
        "checkpoint_sha": "abc1234",
    }


def test_mark_halted_preserves_checkpoint_and_category(tmp_path):
    s = tmp_path / "state.json"
    run("set-checkpoint", "--state", str(s), "--category", "dup-code",
        "--checkpoint", "abc1234")
    r = run("mark-halted", "--state", str(s), "--reason", "3 tests regressed",
            "--head", "def5678")
    assert r.returncode == 0, r.stderr
    d = json.loads(s.read_text())
    assert d["status"] == "halted"
    assert d["category"] == "dup-code"
    assert d["checkpoint_sha"] == "abc1234"
    assert d["halt_reason"] == "3 tests regressed"
    assert d["head_sha"] == "def5678"
    assert "abc1234..def5678" in r.stdout


def test_mark_halted_without_checkpoint_warns(tmp_path):
    s = tmp_path / "state.json"
    r = run("mark-halted", "--state", str(s), "--reason", "x")
    assert "WARNING" in r.stderr
    assert json.loads(s.read_text())["status"] == "halted"


def test_new_checkpoint_clears_a_previous_halt(tmp_path):
    s = tmp_path / "state.json"
    run("set-checkpoint", "--state", str(s), "--category", "a", "--checkpoint", "1")
    run("mark-halted", "--state", str(s), "--reason", "boom", "--head", "2")
    run("set-checkpoint", "--state", str(s), "--category", "b", "--checkpoint", "3")
    d = json.loads(s.read_text())
    assert d["status"] == "in_progress"
    assert "halt_reason" not in d
    assert "head_sha" not in d


def test_read_exits_1_when_halted(tmp_path):
    s = tmp_path / "state.json"
    run("set-checkpoint", "--state", str(s), "--category", "a", "--checkpoint", "1")
    assert run("read", "--state", str(s)).returncode == 0
    run("mark-halted", "--state", str(s), "--reason", "boom", "--head", "2")
    r = run("read", "--state", str(s))
    assert r.returncode == 1
    assert "halted" in r.stdout


def test_read_missing_state_is_not_an_error(tmp_path):
    r = run("read", "--state", str(tmp_path / "nope.json"))
    assert r.returncode == 0
    assert "NO-STATE" in r.stdout


def test_clear_removes_the_file(tmp_path):
    s = tmp_path / "state.json"
    run("set-checkpoint", "--state", str(s), "--category", "a", "--checkpoint", "1")
    assert s.exists()
    r = run("clear", "--state", str(s))
    assert r.returncode == 0
    assert not s.exists()


def test_clear_is_idempotent(tmp_path):
    r = run("clear", "--state", str(tmp_path / "nope.json"))
    assert r.returncode == 0


def test_corrupt_state_is_replaced_not_crashed_on(tmp_path):
    s = tmp_path / "state.json"
    s.write_text("{ not json")
    r = run("set-checkpoint", "--state", str(s), "--category", "a", "--checkpoint", "1")
    assert r.returncode == 0
    assert json.loads(s.read_text())["checkpoint_sha"] == "1"


def test_no_temp_files_left_behind(tmp_path):
    s = tmp_path / "state.json"
    run("set-checkpoint", "--state", str(s), "--category", "a", "--checkpoint", "1")
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_creates_parent_directory(tmp_path):
    s = tmp_path / "nested" / "dir" / "state.json"
    r = run("set-checkpoint", "--state", str(s), "--category", "a", "--checkpoint", "1")
    assert r.returncode == 0, r.stderr
    assert s.exists()
