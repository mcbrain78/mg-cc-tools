"""Post-install configuration for auto-doc.

Adds required Write permissions to settings.local.json and ensures
.mg/ is in .gitignore. Idempotent -- safe to run multiple times.
"""

import argparse
import json
import os


REQUIRED_PERMISSIONS = [
    "Write(path:.mg/)",
    "Write(path:docs/auto-doc/)",
]

GITIGNORE_PATTERNS = [".mg", ".mg/"]


def configure_permissions(settings_path):
    """Add auto-doc Write permissions to settings.local.json.

    Returns list of permissions that were added (empty if all present).
    """
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    perms = settings.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])

    added = []
    for perm in REQUIRED_PERMISSIONS:
        if perm not in allow:
            allow.append(perm)
            added.append(perm)

    if added:
        os.makedirs(os.path.dirname(os.path.abspath(settings_path)), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")

    return added


def configure_gitignore(project_root):
    """Ensure .mg/ is in .gitignore.

    Returns True if entry was added, False if already present.
    """
    gitignore_path = os.path.join(project_root, ".gitignore")

    try:
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []

    if any(line.strip() in GITIGNORE_PATTERNS for line in lines):
        return False

    with open(gitignore_path, "a", encoding="utf-8") as f:
        if lines and lines[-1] != "":
            f.write("\n")
        f.write(".mg/\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Post-install configuration for auto-doc"
    )
    parser.add_argument(
        "--project-root", required=True, help="Target project root directory"
    )
    parser.add_argument(
        "--settings-path", required=True, help="Path to settings.local.json"
    )
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    settings_path = os.path.abspath(args.settings_path)

    # Permissions
    added_perms = configure_permissions(settings_path)
    if added_perms:
        print(f"permissions=ADDED: {', '.join(added_perms)}")
    else:
        print("permissions=OK")

    # Gitignore
    added_gitignore = configure_gitignore(project_root)
    if added_gitignore:
        print("gitignore=ADDED: .mg/")
    else:
        print("gitignore=OK")


if __name__ == "__main__":
    main()
