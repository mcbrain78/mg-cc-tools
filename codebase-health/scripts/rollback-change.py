#!/usr/bin/env python3
"""Undo one failed code change, and report honestly whether it worked.

The implement step applies one finding at a time, tests, and commits. When a
change breaks the tests it has to be undone before the next one starts. Three
earlier attempts at that got it wrong:

  * `git checkout -- .` restores tracked files only and its pathspec is relative
    to the working directory, so a failed change's new file stayed on disk and a
    rollback run from a subdirectory silently reverted only that subtree.
  * `git checkout -- :/` fixed the subdirectory half but still cannot undo a
    STAGED change. Verified: after `git mv old.py new.py` the rename survives it
    completely. Since Refactor-rename and Merge are documented change types,
    every one of them left the tree dirty and halted the run.
  * An untracked-file baseline recorded once per run was used to decide which
    untracked files were the change's own. Over a long run that snapshot goes
    stale, so anything the user dropped into the repo afterwards was classified
    as rollback debris and deleted.

This version drops the baseline entirely. `preflight` asserts the tree is clean
immediately before a change is applied, which makes the baseline unnecessary:
whatever is dirty at rollback time is that change's own footprint, with no
snapshot to go stale. Safety comes from checking at the right moment rather than
from remembering.

Classification is by whether a path exists in HEAD, not by its status code, which
handles every case with one rule:

    in HEAD      -> `git checkout HEAD -- <path>`  (sources from the commit, so
                    it undoes staged edits, staged deletions and mode changes)
    not in HEAD  -> unstage, then remove from disk

A staged rename is two paths under that rule: the old side is in HEAD and gets
restored, the new side is not and gets removed. That is the case every previous
version missed.

Residual risk, stated rather than hidden: if the user edits a tracked file during
the window between preflight and rollback, `git checkout HEAD -- <path>` cannot
tell that edit from the failed change's and will revert both. The window is one
change's Execute+Test, not the whole run, and nothing here closes it further.

Usage:
    rollback-change.py preflight --repo <root> [--exclude <dir>]...
    rollback-change.py rollback  --repo <root> [--exclude <dir>]... [--dry-run]
"""

import argparse
import os
import subprocess
import sys

# The pipeline writes its own findings JSON and reports inside the project while
# it runs, so those paths are never part of a change's footprint. Both layouts
# are excluded by default: a forgotten flag should not make the tool roll back
# its own ledger.
DEFAULT_EXCLUDES = (".mg", ".health-scan")


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=check
    )


def has_head(repo):
    """False in a repo with no commits yet, where nothing can be in HEAD."""
    return git(repo, "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def _unquote(path):
    """Undo git's C-style quoting of paths containing unusual characters."""
    if path.startswith('"') and path.endswith('"'):
        return path[1:-1].encode().decode("unicode_escape")
    return path


def entries(repo, excludes):
    """Dirty paths from git status, both sides of renames, excludes applied.

    Returns a list of (path, status_code) with one entry per affected path.
    """
    out = git(
        repo, "status", "--porcelain", "--untracked-files=all"
    ).stdout
    found = []
    for line in out.splitlines():
        if not line or len(line) < 4:
            continue
        code, rest = line[:2], line[3:]
        paths = []
        if " -> " in rest:
            # Rename or copy: both sides matter.
            old, new = rest.split(" -> ", 1)
            paths = [_unquote(old), _unquote(new)]
        else:
            paths = [_unquote(rest)]
        for p in paths:
            top = p.split("/", 1)[0]
            if top in excludes:
                continue
            found.append((p, code))
    return found


def cmd_preflight(args):
    dirty = entries(args.repo, set(args.excludes))
    if not dirty:
        print("PREFLIGHT: CLEAN -- safe to apply the next change")
        return 0
    print("PREFLIGHT: DIRTY -- the working tree has changes that are not this run's")
    for path, code in sorted(dirty):
        print(f"  {code} {path}")
    print(
        "Applying a change now would make the failed-change rollback unable to tell "
        "these apart from its own edits. Commit, stash or revert them first."
    )
    return 1


def cmd_rollback(args):
    repo = args.repo
    excludes = set(args.excludes)
    dirty = entries(repo, excludes)

    if not dirty:
        print("ROLLBACK: CLEAN -- nothing to undo, tree already matches HEAD")
        return 0

    head = has_head(repo)
    restore, discard = [], []
    for path, _ in dirty:
        in_head = head and git(
            repo, "cat-file", "-e", f"HEAD:{path}", check=False
        ).returncode == 0
        (restore if in_head else discard).append(path)

    if args.dry_run:
        for p in sorted(restore):
            print(f"  would restore from HEAD: {p}")
        for p in sorted(discard):
            print(f"  would unstage and remove: {p}")
        print("DRY-RUN: no changes made")
        return 0

    if restore:
        # One call: git applies it atomically enough for our purposes and it
        # undoes staged content, staged deletions and mode bits together.
        git(repo, "checkout", "HEAD", "--", *sorted(restore))

    removed = []
    for path in sorted(discard):
        abs_path = os.path.join(repo, path)
        # Unstage first so a staged-new file does not linger in the index after
        # its blob is gone from disk.
        git(repo, "reset", "-q", "HEAD", "--", path, check=False)
        try:
            os.remove(abs_path)
            removed.append(path)
        except FileNotFoundError:
            removed.append(path)
        except OSError as exc:
            print(f"WARNING: could not remove {path}: {exc}")
        else:
            parent = os.path.dirname(abs_path)
            if parent and os.path.isdir(parent):
                try:
                    # Stops at the first non-empty parent, so it cannot walk out
                    # of the repo.
                    os.removedirs(parent)
                except OSError:
                    pass

    if restore:
        print(f"RESTORED: {len(restore)} path(s) from HEAD: {', '.join(sorted(restore))}")
    if removed:
        print(f"REMOVED: {len(removed)} path(s) the change created: {', '.join(removed)}")

    leftover = entries(repo, excludes)
    if not leftover:
        print("ROLLBACK: CLEAN -- working tree matches HEAD")
        return 0

    print("ROLLBACK: DIRTY -- the working tree was not fully restored")
    for path, code in sorted(leftover):
        print(f"  {code} {path}")
    print(
        "Record this finding as rollback-failed, not rolled-back, and stop rather "
        "than applying the next change on top of a dirty tree."
    )
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Undo one failed code change, and report whether it worked."
    )
    sub = p.add_subparsers(dest="command", required=True)

    for name, fn, helptext in (
        ("preflight", cmd_preflight, "assert the tree is clean before a change"),
        ("rollback", cmd_rollback, "undo the change that just failed, and verify"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--repo", required=True)
        sp.add_argument(
            "--exclude",
            action="append",
            dest="excludes",
            default=None,
            help=f"top-level dir to ignore (repeatable; default: {' '.join(DEFAULT_EXCLUDES)})",
        )
        if name == "rollback":
            sp.add_argument("--dry-run", action="store_true")
        sp.set_defaults(func=fn)

    args = p.parse_args(argv)
    if args.excludes is None:
        args.excludes = list(DEFAULT_EXCLUDES)

    if git(args.repo, "rev-parse", "--git-dir", check=False).returncode != 0:
        print(f"ERROR: {args.repo} is not a git repository", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
