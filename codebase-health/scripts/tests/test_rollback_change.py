"""Tests for rollback-change.py.

Written against the failures three earlier versions of this rollback had: staged
changes surviving it, a cwd-relative pathspec reverting only a subtree, and a
once-per-run untracked baseline going stale and deleting the user's files. The
staged-rename case is the one that halted real runs, so it is covered from
several angles.
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
    (repo / "mode.sh").write_text("#!/bin/sh\n")
    (repo / "sub" / "s.txt").write_text("original\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def status(repo):
    return git(repo, "status", "--porcelain").stdout


def rollback(repo, *extra, cwd=None):
    return run("rollback", "--repo", str(repo), *extra, cwd=cwd)


# ── the staged-rename bug that halted runs ──────────────────────────────────


def test_staged_rename_is_fully_undone(tmp_path):
    """`git checkout -- :/` left the rename intact; this must undo both sides."""
    repo = make_repo(tmp_path)
    git(repo, "mv", "tracked.txt", "renamed.txt")

    r = rollback(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ROLLBACK: CLEAN" in r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"
    assert not (repo / "renamed.txt").exists()
    assert status(repo) == ""


def test_unstaged_rename_by_hand_is_undone(tmp_path):
    """Same shape, but done with plain filesystem moves rather than git mv."""
    repo = make_repo(tmp_path)
    (repo / "renamed.txt").write_text((repo / "tracked.txt").read_text())
    (repo / "tracked.txt").unlink()

    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"
    assert not (repo / "renamed.txt").exists()


def test_extract_refactor_shape_is_undone(tmp_path):
    """The documented Refactor: Extract case -- edit a file, create a new one."""
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("shortened\n")
    (repo / "extracted.py").write_text("moved code\n")
    git(repo, "add", "-A")

    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"
    assert not (repo / "extracted.py").exists()
    assert status(repo) == ""


# ── staged variants of everything ───────────────────────────────────────────


def test_staged_content_edit_is_undone(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("broken\n")
    git(repo, "add", "tracked.txt")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"


def test_staged_deletion_is_undone(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "rm", "-q", "tracked.txt")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"


def test_staged_new_file_is_removed_and_unstaged(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "new.py").write_text("x\n")
    git(repo, "add", "new.py")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert not (repo / "new.py").exists()
    assert status(repo) == ""


def test_mode_change_is_undone(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "mode.sh").chmod(0o755)
    git(repo, "add", "mode.sh")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert "100644" in git(repo, "ls-files", "-s", "mode.sh").stdout


def test_untracked_file_is_removed(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "stray.py").write_text("x\n")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert not (repo / "stray.py").exists()


def test_new_directory_is_pruned_when_emptied(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "newpkg").mkdir()
    (repo / "newpkg" / "mod.py").write_text("x\n")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert not (repo / "newpkg").exists()


# ── the cwd-relative pathspec bug ───────────────────────────────────────────


def test_rollback_from_a_subdirectory_covers_the_whole_repo(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("broken\n")
    (repo / "sub" / "s.txt").write_text("broken\n")

    r = rollback(repo, cwd=str(repo / "sub"))
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "tracked.txt").read_text() == "original\n"
    assert (repo / "sub" / "s.txt").read_text() == "original\n"


# ── preflight replaces the stale baseline ───────────────────────────────────


def test_preflight_clean_on_a_clean_tree(tmp_path):
    repo = make_repo(tmp_path)
    r = run("preflight", "--repo", str(repo))
    assert r.returncode == 0
    assert "PREFLIGHT: CLEAN" in r.stdout


def test_preflight_catches_a_foreign_edit_before_a_change_is_applied(tmp_path):
    """This is the safety boundary: rollback is unscoped by design, so the
    guarantee comes from refusing to start on a tree that is already dirty."""
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("someone else's work\n")

    r = run("preflight", "--repo", str(repo))
    assert r.returncode == 1
    assert "PREFLIGHT: DIRTY" in r.stdout
    assert "tracked.txt" in r.stdout
    # And it must not have "fixed" anything itself.
    assert (repo / "tracked.txt").read_text() == "someone else's work\n"


def test_preflight_catches_a_foreign_untracked_file(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "my_notes.txt").write_text("mine\n")
    r = run("preflight", "--repo", str(repo))
    assert r.returncode == 1
    assert "my_notes.txt" in r.stdout
    assert (repo / "my_notes.txt").exists()


# ── the workspace exclusion ─────────────────────────────────────────────────


def test_preflight_ignores_the_pipeline_workspace(tmp_path):
    """The tool writes its own findings JSON while it runs; that is not a change."""
    repo = make_repo(tmp_path)
    (repo / ".mg").mkdir()
    (repo / ".mg" / "health-scan-findings.json").write_text("{}\n")
    r = run("preflight", "--repo", str(repo))
    assert r.returncode == 0, r.stdout
    assert "PREFLIGHT: CLEAN" in r.stdout


def test_rollback_never_touches_the_workspace(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".health-scan").mkdir()
    (repo / ".health-scan" / "findings.json").write_text("{}\n")
    (repo / "stray.py").write_text("x\n")

    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / ".health-scan" / "findings.json").read_text() == "{}\n"
    assert not (repo / "stray.py").exists()


def test_exclude_flag_overrides_the_default(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "scratch").mkdir()
    (repo / "scratch" / "x.txt").write_text("x\n")
    r = run("preflight", "--repo", str(repo), "--exclude", "scratch")
    assert r.returncode == 0, r.stdout


# ── misc ────────────────────────────────────────────────────────────────────


def test_clean_tree_rollback_is_a_noop(tmp_path):
    repo = make_repo(tmp_path)
    r = rollback(repo)
    assert r.returncode == 0
    assert "nothing to undo" in r.stdout


def test_dry_run_changes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("broken\n")
    (repo / "new.py").write_text("x\n")
    r = rollback(repo, "--dry-run")
    assert "DRY-RUN" in r.stdout
    assert (repo / "tracked.txt").read_text() == "broken\n"
    assert (repo / "new.py").exists()


def test_repo_with_no_commits_removes_everything_it_finds(tmp_path):
    """Unborn HEAD: nothing can be restored, so every path is discardable."""
    repo = tmp_path / "fresh"
    repo.mkdir()
    git(repo.parent, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("x\n")
    r = rollback(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (repo / "a.py").exists()


def test_path_with_spaces_is_handled(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a file with spaces.py").write_text("x\n")
    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert not (repo / "a file with spaces.py").exists()


def test_gitignored_file_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text("*.log\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore")
    (repo / "debug.log").write_text("noise\n")
    (repo / "stray.py").write_text("x\n")

    r = rollback(repo)
    assert "ROLLBACK: CLEAN" in r.stdout, r.stdout
    assert (repo / "debug.log").exists()
    assert not (repo / "stray.py").exists()


def test_non_repo_is_an_error(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    r = rollback(d)
    assert r.returncode == 2
    assert "not a git repository" in r.stderr
