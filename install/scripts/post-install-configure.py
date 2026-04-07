#!/usr/bin/env python3
"""post-install-configure.py -- configure permissions and gitignore for mg-cc-tools.

Adds Write permissions to settings.local.json and ensures .mg/ is in .gitignore.
Both operations are idempotent.

Usage:
    python3 post-install-configure.py \
        --project-root /path/to/project \
        --settings-path /path/to/project/.claude/settings.local.json

Output (one line per operation):
    permissions=ADDED  or  permissions=OK
    gitignore=ADDED    or  gitignore=OK

Zero pip dependencies -- all stdlib.
"""

import argparse
import json
import sys
from pathlib import Path

# Permissions to ensure in settings.local.json
REQUIRED_PERMISSIONS = [
    "Write(path:.mg/)",
    "Write(path:docs/auto-doc/)",
]

GITIGNORE_ENTRY = ".mg/"


def configure_permissions(settings_path: Path) -> str:
    """Ensure REQUIRED_PERMISSIONS are in settings.local.json allow list.

    Creates the file and parent directories if they don't exist.

    Returns:
        "ADDED" if any permissions were added, "OK" if all already present.
    """
    # Read existing settings or start fresh
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: Failed to parse {settings_path}: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        data = {}

    # Navigate to permissions.allow, creating structure if needed
    permissions = data.setdefault("permissions", {})
    allow_list = permissions.setdefault("allow", [])

    # Add missing permissions
    added = False
    for perm in REQUIRED_PERMISSIONS:
        if perm not in allow_list:
            allow_list.append(perm)
            added = True

    if added:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    return "ADDED" if added else "OK"


def configure_gitignore(project_root: Path) -> str:
    """Ensure GITIGNORE_ENTRY is in .gitignore.

    Creates the file if it doesn't exist.

    Returns:
        "ADDED" if the entry was added, "OK" if already present.
    """
    gitignore_path = project_root / ".gitignore"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Check if .mg/ is already listed (exact line match, stripped)
        for line in lines:
            if line.strip() == GITIGNORE_ENTRY:
                return "OK"

        # Append with a preceding newline if file doesn't end with one
        if content and not content.endswith("\n"):
            content += "\n"
        content += GITIGNORE_ENTRY + "\n"
        gitignore_path.write_text(content, encoding="utf-8")
        return "ADDED"
    else:
        gitignore_path.write_text(GITIGNORE_ENTRY + "\n", encoding="utf-8")
        return "ADDED"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure permissions and gitignore for mg-cc-tools post-install."
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Path to the target project root directory.",
    )
    parser.add_argument(
        "--settings-path",
        required=True,
        help="Path to the target project's settings.local.json.",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root)
    settings_path = Path(args.settings_path)

    if not project_root.is_dir():
        print(f"ERROR: Project root not found: {project_root}", file=sys.stderr)
        sys.exit(1)

    perm_status = configure_permissions(settings_path)
    print(f"permissions={perm_status}")

    gitignore_status = configure_gitignore(project_root)
    print(f"gitignore={gitignore_status}")


if __name__ == "__main__":
    main()
