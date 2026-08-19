"""Tests for archive-run.py."""

import os
import subprocess
import sys

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "archive-run.py")


def _run(run_dir, history_dir, prefix="audit", sentinel="summary.md"):
    return subprocess.run(
        [
            sys.executable, SCRIPT,
            "--run-dir", str(run_dir),
            "--history-dir", str(history_dir),
            "--prefix", prefix,
            "--sentinel", sentinel,
        ],
        capture_output=True,
        text=True,
    )


def _make_run(tmp_path, sentinel: str | None = "summary.md", name="run"):
    run_dir = tmp_path / name
    run_dir.mkdir()
    if sentinel:
        (run_dir / sentinel).write_text("done")
    (run_dir / "payload.json").write_text("[]")
    return run_dir


def test_archives_completed_run_as_number_1(tmp_path):
    run_dir = _make_run(tmp_path)
    hist = tmp_path / "history"

    r = _run(run_dir, hist)

    assert r.returncode == 0, r.stderr
    assert "ARCHIVED:" in r.stdout
    assert not run_dir.exists()
    assert (hist / "audit-1" / "payload.json").read_text() == "[]"


def test_second_archive_gets_number_2(tmp_path):
    hist = tmp_path / "history"
    _run(_make_run(tmp_path), hist)
    _run(_make_run(tmp_path), hist)

    assert sorted(os.listdir(hist)) == ["audit-1", "audit-2"]


def test_numbering_is_max_plus_one_not_a_count(tmp_path):
    """A deleted archive must not cause the next run to reuse a live number."""
    hist = tmp_path / "history"
    _run(_make_run(tmp_path), hist)
    _run(_make_run(tmp_path), hist)
    _run(_make_run(tmp_path), hist)
    # Remove the middle one: count is now 2, but audit-3 exists.
    for entry in (hist / "audit-2").iterdir():
        entry.unlink()
    (hist / "audit-2").rmdir()

    _run(_make_run(tmp_path), hist)

    assert sorted(os.listdir(hist)) == ["audit-1", "audit-3", "audit-4"]


def test_run_without_sentinel_is_not_archived(tmp_path):
    run_dir = _make_run(tmp_path, sentinel=None)
    hist = tmp_path / "history"

    r = _run(run_dir, hist)

    assert r.returncode == 0
    assert "SKIPPED:" in r.stdout
    assert "summary.md" in r.stdout
    assert run_dir.exists(), "an interrupted run must be left in place"
    assert not hist.exists()


def test_missing_run_dir_is_not_an_error(tmp_path):
    r = _run(tmp_path / "nope", tmp_path / "history")

    assert r.returncode == 0
    assert "SKIPPED:" in r.stdout


def test_history_dir_is_created(tmp_path):
    hist = tmp_path / "deep" / "history"
    _run(_make_run(tmp_path), hist)

    assert (hist / "audit-1").is_dir()


def test_prefix_separates_two_run_types_in_one_history(tmp_path):
    """auditv2 and fix share a history dir; the prefix is what tells them apart."""
    hist = tmp_path / "history"
    _run(_make_run(tmp_path, name="run"), hist, prefix="audit")
    _run(
        _make_run(tmp_path, sentinel="fix-state.json", name="fix"),
        hist,
        prefix="fix",
        sentinel="fix-state.json",
    )
    _run(_make_run(tmp_path, name="run2"), hist, prefix="audit")

    assert sorted(os.listdir(hist)) == ["audit-1", "audit-2", "fix-1"]


def test_wrong_sentinel_name_does_not_archive(tmp_path):
    run_dir = _make_run(tmp_path, sentinel="summary.md")
    hist = tmp_path / "history"

    r = _run(run_dir, hist, sentinel="fix-state.json")

    assert "SKIPPED:" in r.stdout
    assert run_dir.exists()


def test_existing_history_is_never_written_into(tmp_path):
    hist = tmp_path / "history"
    hist.mkdir()
    (hist / "audit-1").mkdir()
    (hist / "audit-1" / "old.txt").write_text("precious")

    r = _run(_make_run(tmp_path), hist)

    assert r.returncode == 0, r.stderr
    assert (hist / "audit-1" / "old.txt").read_text() == "precious"
    assert (hist / "audit-2" / "payload.json").exists()


def test_unrelated_directory_names_do_not_affect_numbering(tmp_path):
    hist = tmp_path / "history"
    hist.mkdir()
    (hist / "audit-notes").mkdir()
    (hist / "audit-12x").mkdir()
    (hist / "fix-9").mkdir()

    _run(_make_run(tmp_path), hist)

    assert (hist / "audit-1").is_dir()
