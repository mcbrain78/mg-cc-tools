"""Tests for affected-sections.py."""

import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "affected-sections.py")


def _run(uncleared, output):
    return subprocess.run(
        [
            sys.executable, SCRIPT,
            "--uncleared-file", str(uncleared),
            "--output", str(output),
        ],
        capture_output=True,
        text=True,
    )


def _write(path, data):
    path.write_text(json.dumps(data))
    return path


def test_collects_distinct_sections_sorted(tmp_path):
    uncleared = _write(tmp_path / "u.json", [
        {"entity": "b", "section": "Setup/Install"},
        {"entity": "a", "section": "Intro"},
        {"entity": "c", "section": "Setup/Install"},
    ])
    out = tmp_path / "affected.json"

    r = _run(uncleared, out)

    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text()) == ["Intro", "Setup/Install"]
    assert r.stdout.startswith("AFFECTED: 2 section(s)")


def test_empty_uncleared_reports_no_sections_and_writes_empty_filter(tmp_path):
    uncleared = _write(tmp_path / "u.json", [])
    out = tmp_path / "affected.json"

    r = _run(uncleared, out)

    assert r.returncode == 0
    assert r.stdout.startswith("NO-SECTIONS:")
    assert json.loads(out.read_text()) == []


def test_stale_filter_is_overwritten_when_work_runs_out(tmp_path):
    """The between-waves case: a filter from the previous wave must not survive."""
    out = tmp_path / "affected.json"
    _write(out, ["Intro", "Setup"])
    uncleared = _write(tmp_path / "u.json", [])

    _run(uncleared, out)

    assert json.loads(out.read_text()) == []


def test_missing_uncleared_file_is_not_an_error(tmp_path):
    r = _run(tmp_path / "nope.json", tmp_path / "affected.json")

    assert r.returncode == 0
    assert r.stdout.startswith("NO-SECTIONS:")


def test_entries_without_a_section_are_ignored(tmp_path):
    uncleared = _write(tmp_path / "u.json", [
        {"entity": "a"},
        {"entity": "b", "section": ""},
        {"entity": "c", "section": "Intro"},
    ])
    out = tmp_path / "affected.json"

    r = _run(uncleared, out)

    assert json.loads(out.read_text()) == ["Intro"]
    assert r.stdout.startswith("AFFECTED: 1 section(s)")


def test_entries_that_all_lack_sections_report_why(tmp_path):
    uncleared = _write(tmp_path / "u.json", [{"entity": "a"}, {"entity": "b"}])

    r = _run(uncleared, tmp_path / "affected.json")

    assert r.returncode == 0
    assert "2 uncleared entr(ies) but none name a section" in r.stdout


def test_malformed_json_is_an_error(tmp_path):
    bad = tmp_path / "u.json"
    bad.write_text("{ not json")

    r = _run(bad, tmp_path / "affected.json")

    assert r.returncode == 1
    assert "ERROR" in r.stderr


def test_non_array_uncleared_is_an_error(tmp_path):
    uncleared = _write(tmp_path / "u.json", {"section": "Intro"})

    r = _run(uncleared, tmp_path / "affected.json")

    assert r.returncode == 1
    assert "JSON array" in r.stderr


def test_output_parent_directory_is_created(tmp_path):
    uncleared = _write(tmp_path / "u.json", [{"section": "Intro"}])
    out = tmp_path / "prose-verify-devops-OPERATIONS" / "affected-sections.json"

    r = _run(uncleared, out)

    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text()) == ["Intro"]
