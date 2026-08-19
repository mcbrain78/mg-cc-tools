"""Tests for rollback-change.py.

Written against the two failures the old `git checkout -- .` had: untracked
files surviving a rollback that was then reported as clean, and the `.` pathspec
being relative to the working directory.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rollback-change.py"


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd
    )


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    git(repo.parent, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "tracked.txt").write_text("original\n")
    (repo / "sub" / "s.txt").write_text("original\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def status(repo):
    return git(repo, "status", "--porcelain").stdout


# ── the untracked-file bug ──────────────────────────────────────────────────


def test_untracked_file_from_failed_change_is_removed(tmp_path):
    repo = make_repo(tmp_path)
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    # A failed "Refactor: Extract" — modifies a tracked file and creates a new one.
    (repo / "tracked.txt").write_text("broken\n")
    (repo / "new_module.py").write_text("extracted\n")

    r = run("rollback", "--repo", str(repo), "--baseline", str(base))
    assert r.returncode == 0, r.stdout
    assert "ROLLBACK: CLEAN" in r.stdout
    assert not (repo / "new_module.py").exists()
    assert (repo / "tracked.txt").read_text() == "original\n"
    assert status(repo) == ""


def test_reports_dirty_rather_than_clean_when_a_file_survives(tmp_path):
    """Without a baseline nothing is deleted, so the result must not claim clean."""
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("broken\n")
    (repo / "new_module.py").write_text("extracted\n")

    r = run("rollback", "--repo", str(repo))
    assert r.returncode == 1
    assert "ROLLBACK: DIRTY" in r.stdout
    assert "still untracked: new_module.py" in r.stdout
    assert "rollback-failed" in r.stdout
    # Tracked modifications are still reverted.
    assert (repo / "tracked.txt").read_text() == "original\n"
    # And the user's file is left alone rather than guessed at.
    assert (repo / "new_module.py").exists()


def test_missing_baseline_file_warns_and_deletes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "stray.py").write_text("x\n")
    r = run("rollback", "--repo", str(repo), "--baseline", str(tmp_path / "nope.txt"))
    assert "not found" in r.stdout
    assert (repo / "stray.py").exists()
    assert r.returncode == 1


# ── the cwd-relative pathspec bug ───────────────────────────────────────────


def test_rollback_from_a_subdirectory_reverts_the_whole_repo(tmp_path):
    """`git checkout -- .` from sub/ left root modifications in place."""
    repo = make_repo(tmp_path)
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    (repo / "tracked.txt").write_text("broken\n")
    (repo / "sub" / "s.txt").write_text("broken\n")

    r = run(
        "rollback", "--repo", str(repo), "--baseline", str(base), cwd=str(repo / "sub")
    )
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"
    assert (repo / "sub" / "s.txt").read_text() == "original\n"


# ── baseline discrimination ─────────────────────────────────────────────────


def test_pre_existing_untracked_file_is_preserved(tmp_path):
    """A file the user had lying around must survive a rollback."""
    repo = make_repo(tmp_path)
    (repo / "my_notes.txt").write_text("mine\n")
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    (repo / "new_module.py").write_text("extracted\n")
    r = run("rollback", "--repo", str(repo), "--baseline", str(base))

    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "my_notes.txt").read_text() == "mine\n"
    assert not (repo / "new_module.py").exists()


def test_baseline_records_existing_untracked_files(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("a\n")
    (repo / "sub" / "b.txt").write_text("b\n")
    base = tmp_path / "baseline.txt"
    r = run("baseline", "--repo", str(repo), "--out", str(base))
    assert "recorded 2" in r.stdout
    assert set(base.read_text().split()) == {"a.txt", "sub/b.txt"}


def test_gitignored_file_is_not_touched(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text("*.log\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore")
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    (repo / "debug.log").write_text("noise\n")
    (repo / "new_module.py").write_text("extracted\n")
    r = run("rollback", "--repo", str(repo), "--baseline", str(base))

    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "debug.log").exists()
    assert not (repo / "new_module.py").exists()


# ── new directories, staged changes, misc ───────────────────────────────────


def test_new_directory_is_pruned_when_emptied(tmp_path):
    repo = make_repo(tmp_path)
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    (repo / "newpkg").mkdir()
    (repo / "newpkg" / "mod.py").write_text("x\n")
    r = run("rollback", "--repo", str(repo), "--baseline", str(base))

    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert not (repo / "newpkg").exists()


def test_staged_modification_is_reverted(tmp_path):
    repo = make_repo(tmp_path)
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    (repo / "tracked.txt").write_text("broken\n")
    git(repo, "add", "tracked.txt")
    r = run("rollback", "--repo", str(repo), "--baseline", str(base))

    # `git checkout -- :/` restores the worktree from the index, so a staged
    # change stays staged; the point is that the caller is told, not that the
    # rollback silently claims success.
    assert "ROLLBACK: DIRTY" in r.stdout
    assert r.returncode == 1


def test_clean_tree_rolls_back_to_clean(tmp_path):
    repo = make_repo(tmp_path)
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))
    r = run("rollback", "--repo", str(repo), "--baseline", str(base))
    assert "ROLLBACK: CLEAN" in r.stdout
    assert r.returncode == 0


def test_dry_run_changes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    base = tmp_path / "baseline.txt"
    run("baseline", "--repo", str(repo), "--out", str(base))

    (repo / "tracked.txt").write_text("broken\n")
    (repo / "new_module.py").write_text("extracted\n")
    r = run("rollback", "--repo", str(repo), "--baseline", str(base), "--dry-run")

    assert (repo / "tracked.txt").read_text() == "broken\n"
    assert (repo / "new_module.py").exists()
    assert "new_module.py" in r.stdout


def test_non_repo_is_an_error(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    r = run("rollback", "--repo", str(d))
    assert r.returncode == 2
    assert "not a git repository" in r.stderr
