#!/usr/bin/env python3
"""File operations for the spec-improve workflow.

Single source of truth for naming conventions and all deterministic
file operations.  The LLM command orchestrates; this script acts.

Naming conventions (given ``concept.md``):
    original backup : concept.original.md
    working copy    : concept-auto-improve.md
    non-goals       : concept-NON-GOALS.md

Subcommands
-----------
init <file>
    Back up the original (once), create the working copy, and print a
    JSON object with all resolved paths so the LLM knows where
    everything lives.

approve <file>
    Copy the working copy over the original and delete the working copy.

reject <file>
    Delete the working copy, leaving the original untouched.

append-non-goal <file> <text>
    Append a non-goal entry to the non-goals file (created if absent).

Exit codes: 0 = success, 1 = error (details on stderr).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


# ── Naming conventions (single source of truth) ────────────────────────────


def _original_path(source: Path) -> Path:
    """concept.md → concept.original.md"""
    return source.with_suffix(f".original{source.suffix}")


def _auto_improve_path(source: Path) -> Path:
    """concept.md → concept-auto-improve.md"""
    return source.with_stem(f"{source.stem}-auto-improve")


def _non_goals_path(source: Path) -> Path:
    """concept.md → concept-NON-GOALS.md"""
    return source.with_stem(f"{source.stem}-NON-GOALS")


# ── Subcommands ─────────────────────────────────────────────────────────────


def cmd_init(source: Path) -> int:
    """Back up original, create working copy, emit path JSON."""
    if not source.is_file():
        print(f"Error: source file not found: {source}", file=sys.stderr)
        return 1

    backup = _original_path(source)
    backup_created = False
    if not backup.exists():
        shutil.copy2(source, backup)
        backup_created = True

    working = _auto_improve_path(source)
    shutil.copy2(source, working)

    non_goals = _non_goals_path(source)

    result = {
        "auto_improve": str(working),
        "non_goals": str(non_goals),
        "non_goals_exists": non_goals.is_file(),
        "original_backup": str(backup),
        "backup_created": backup_created,
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_approve(source: Path) -> int:
    """Copy working copy over original, delete working copy."""
    working = _auto_improve_path(source)
    if not working.is_file():
        print(f"Error: working copy not found: {working}", file=sys.stderr)
        return 1

    shutil.copy2(working, source)
    working.unlink()
    print(f"Approved: {working} → {source}")
    return 0


def cmd_reject(source: Path) -> int:
    """Delete working copy, leave original untouched."""
    working = _auto_improve_path(source)
    if not working.is_file():
        print(f"Error: working copy not found: {working}", file=sys.stderr)
        return 1

    working.unlink()
    print(f"Rejected: deleted {working}")
    return 0


def cmd_append_non_goal(source: Path, text: str) -> int:
    """Append a non-goal entry to the non-goals file."""
    non_goals = _non_goals_path(source)

    if non_goals.is_file():
        content = non_goals.read_text()
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = f"# Non-Goals for {source.name}\n\n"

    content += f"- {text}\n"
    non_goals.write_text(content)
    print(f"Appended non-goal to {non_goals}")
    return 0


# ── CLI dispatch ────────────────────────────────────────────────────────────

USAGE = """\
Usage: improve_files.py <command> <file> [args...]

Commands:
  init              <file>          Back up original, create working copy, emit paths JSON
  approve           <file>          Copy working copy over original, delete working copy
  reject            <file>          Delete working copy
  append-non-goal   <file> <text>   Append entry to non-goals file
"""


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        print(USAGE, file=sys.stderr)
        return 1

    command, file_arg = args[0], args[1]
    source = Path(file_arg)

    if command == "init":
        return cmd_init(source)
    elif command == "approve":
        return cmd_approve(source)
    elif command == "reject":
        return cmd_reject(source)
    elif command == "append-non-goal":
        if len(args) < 3:
            print("Error: append-non-goal requires <file> and <text>", file=sys.stderr)
            return 1
        return cmd_append_non_goal(source, args[2])
    else:
        print(f"Error: unknown command: {command}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
