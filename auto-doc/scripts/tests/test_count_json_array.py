"""Tests for count-json-array.py."""

import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "count-json-array.py")


def _run(path):
    return subprocess.run(
        [sys.executable, SCRIPT, "--file", str(path)],
        capture_output=True,
        text=True,
    )


def test_counts_elements(tmp_path):
    f = tmp_path / "dismissed.json"
    f.write_text(json.dumps([{"entity": "a"}, {"entity": "b"}, {"entity": "c"}]))

    r = _run(f)

    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "3"


def test_empty_array_is_zero(tmp_path):
    f = tmp_path / "dismissed.json"
    f.write_text("[]")

    r = _run(f)

    assert r.returncode == 0
    assert r.stdout.strip() == "0"


def test_missing_file_is_zero_not_an_error(tmp_path):
    r = _run(tmp_path / "never-written.json")

    assert r.returncode == 0
    assert r.stdout.strip() == "0"


def test_malformed_json_is_an_error(tmp_path):
    f = tmp_path / "dismissed.json"
    f.write_text("[{,]")

    r = _run(f)

    assert r.returncode == 1
    assert r.stdout.strip() == ""
    assert "not valid JSON" in r.stderr


def test_object_instead_of_array_is_an_error(tmp_path):
    f = tmp_path / "dismissed.json"
    f.write_text(json.dumps({"entity": "a"}))

    r = _run(f)

    assert r.returncode == 1
    assert "expected a JSON array" in r.stderr


def test_prints_only_the_number(tmp_path):
    """The caller branches on this value, so nothing else may share stdout."""
    f = tmp_path / "dismissed.json"
    f.write_text(json.dumps([1, 2]))

    r = _run(f)

    assert r.stdout == "2\n"
