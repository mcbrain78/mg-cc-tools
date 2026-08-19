#!/usr/bin/env python3
"""Roll back a failed code change, and report honestly whether it worked.

The implement step used to roll back with a bare `git checkout -- .` and then
record the finding as `rolled-back`, on the stated grounds that committing after
every success means only the current change can be affected. Two things were
wrong with that:

  * `git checkout` restores tracked files. It does not touch untracked ones, so
    a failed "Refactor: Extract..." or "Merge: Combine duplicates" -- both
    file-creating change types the step documents -- left its new file sitting on
    disk while the finding was reported as cleanly rolled back.
  * The `.` pathspec is relative to the working directory. Run from a
    subdirectory it silently reverts only that subtree, leaving modifications
    elsewhere in the repo in place. `:/` anchors to the repo root instead.

So the rollback reverts tracked files repo-wide, removes exactly the untracked
files that appeared since the baseline, and then re-checks the tree. It reports
CLEAN only when nothing is left over, and DIRTY (with the paths) when something
is -- because "I could not fully undo this" is the one thing the caller must not
paper over when deciding what to record.

Deleting untracked files needs a baseline to be safe: without one there is no
way to distinguish a file the failed change created from a file the user left
lying around. With no baseline the script reverts tracked files, reports what it
found, and deletes nothing.

Usage:
    rollback-change.py baseline --repo <root> --out <file>
    rollback-change.py rollback --repo <root> [--baseline <file>] [--dry-run]
"""

import argparse
import os
import subprocess
import sys


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=check
    )


def untracked(repo):
    """Untracked, non-ignored files, as repo-relative paths."""
    out = git(repo, "ls-files", "--others", "--exclude-standard").stdout
    return {line for line in out.splitlines() if line}


def modified(repo):
    """Tracked files with unstaged or staged modifications."""
    out = git(repo, "status", "--porcelain", "--untracked-files=no").stdout
    paths = set()
    for line in out.splitlines():
        if not line:
            continue
        # Porcelain v1: 2 status chars, a space, then the path (or "old -> new").
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path.strip('"'))
    return paths


def cmd_baseline(args):
    paths = sorted(untracked(args.repo))
    with open(args.out, "w") as f:
        for p in paths:
            f.write(p + "\n")
    print(f"BASELINE: recorded {len(paths)} pre-existing untracked file(s) to {args.out}")
    return 0


def cmd_rollback(args):
    repo = args.repo

    baseline = None
    if args.baseline:
        try:
            with open(args.baseline) as f:
                baseline = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            print(
                f"WARNING: baseline {args.baseline} not found; "
                "reverting tracked files only and deleting nothing"
            )

    # Revert tracked modifications repo-wide. `:/` is the repo root regardless of
    # the caller's working directory, which `.` is not.
    if not args.dry_run:
        git(repo, "checkout", "--", ":/")

    leftover_untracked = untracked(repo)
    if baseline is None:
        stray = set()
        undeletable = leftover_untracked
    else:
        stray = leftover_untracked - baseline
        undeletable = set()

    removed = []
    for rel in sorted(stray):
        abs_path = os.path.join(repo, rel)
        if args.dry_run:
            removed.append(rel)
            continue
        try:
            os.remove(abs_path)
            removed.append(rel)
        except OSError as exc:
            print(f"WARNING: could not remove {rel}: {exc}")
            undeletable.add(rel)
        else:
            # Prune directories the removal just emptied. removedirs stops at the
            # first non-empty parent, so this cannot walk out of the repo.
            parent = os.path.dirname(abs_path)
            if parent and os.path.isdir(parent):
                try:
                    os.removedirs(parent)
                except OSError:
                    pass

    still_modified = modified(repo)
    still_untracked = (untracked(repo) - (baseline or set())) | undeletable

    if removed:
        print(
            f"REMOVED: {len(removed)} untracked file(s) created by the failed change: "
            + ", ".join(removed)
        )

    if not still_modified and not still_untracked:
        print("ROLLBACK: CLEAN -- working tree matches the last commit")
        return 0

    print("ROLLBACK: DIRTY -- the working tree was not fully restored")
    for p in sorted(still_modified):
        print(f"  still modified:  {p}")
    for p in sorted(still_untracked):
        print(f"  still untracked: {p}")
    print(
        "Record this finding as rollback-failed, not rolled-back, and stop rather "
        "than applying the next change on top of a dirty tree."
    )
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Roll back a failed code change, and report honestly whether it worked."
    )
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("baseline", help="record pre-existing untracked files")
    b.add_argument("--repo", required=True)
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_baseline)

    r = sub.add_parser("rollback", help="revert a failed change and verify")
    r.add_argument("--repo", required=True)
    r.add_argument("--baseline", help="baseline file from the `baseline` command")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_rollback)

    args = p.parse_args(argv)
    if not os.path.isdir(os.path.join(args.repo, ".git")):
        # A worktree or submodule has a .git file rather than a directory; only
        # bail when git itself does not recognise the path.
        probe = git(args.repo, "rev-parse", "--git-dir", check=False)
        if probe.returncode != 0:
            print(f"ERROR: {args.repo} is not a git repository", file=sys.stderr)
            return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
