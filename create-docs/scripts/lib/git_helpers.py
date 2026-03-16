"""Git subprocess wrappers for create-docs scripts.

Provides helpers to query git history for staleness checks and
source material tracking. All subprocess calls use explicit
encoding="utf-8" to avoid platform-dependent encoding issues.

Zero external dependencies -- stdlib only.
"""

import os
import subprocess


def git_log_since(path, since_date, repo_root=None):
    """Return commits touching path since a given date.

    Runs: git log --format="%H %ai" --since={since_date} -- {path}

    Args:
        path: File or directory path to check (relative to repo root).
        since_date: ISO date string (e.g. "2025-01-15").
        repo_root: Working directory for git command. If None, uses
            the current working directory.

    Returns:
        List of (commit_hash, date_str) tuples. Empty list if no
        commits found or git command fails.
    """
    cmd = [
        "git", "log",
        "--format=%H %ai",
        f"--since={since_date}",
        "--", path,
    ]
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
    }
    if repo_root:
        kwargs["cwd"] = repo_root

    try:
        result = subprocess.run(cmd, **kwargs)
        if result.returncode != 0:
            return []
    except (subprocess.SubprocessError, OSError):
        return []

    entries = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "<40-char-hash> <date> <time> <tz>"
        parts = line.split(" ", 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1]))
    return entries


def git_file_changed_since(path, since_date, repo_root=None):
    """Check whether a file has any commits since a given date.

    Args:
        path: File path to check (relative to repo root).
        since_date: ISO date string (e.g. "2025-01-15").
        repo_root: Working directory for git command.

    Returns:
        True if at least one commit exists for path since since_date,
        False otherwise.
    """
    return len(git_log_since(path, since_date, repo_root=repo_root)) > 0


def git_last_modified(path, repo_root=None):
    """Return the date of the most recent commit touching a file.

    Runs: git log -1 --format="%ai" -- {path}

    Args:
        path: File path to check (relative to repo root).
        repo_root: Working directory for git command.

    Returns:
        ISO date string (e.g. "2025-01-15 14:30:00 +0000") or None
        if the file has no git history or the command fails.
    """
    cmd = [
        "git", "log", "-1",
        "--format=%ai",
        "--", path,
    ]
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
    }
    if repo_root:
        kwargs["cwd"] = repo_root

    try:
        result = subprocess.run(cmd, **kwargs)
        if result.returncode != 0:
            return None
    except (subprocess.SubprocessError, OSError):
        return None

    output = result.stdout.strip()
    return output if output else None
