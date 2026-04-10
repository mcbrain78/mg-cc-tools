#!/usr/bin/env python3
"""Dismiss an entity from the uncleared list into a per-run dismissals file.

When the resolution agent determines an entity is not ref-worthy (e.g.,
a generic tool name, formatting artifact, or system username), this script:
1. Checks if the entity is in the protected-entities list (if provided).
   If protected: refuses silently and leaves uncleared unchanged.
2. Removes ALL entries with that entity name from the uncleared file.
3. Appends the entity to the per-run dismissed-this-run file (deduped).

Dismissed entities are later classified by a post-wave agent into either
permanent not-entities or protected-entities lists.

Usage:
    python3 dismiss-entity.py \
        --entity NAME \
        --section SECTION \
        --uncleared-file FILE \
        --dismissed-this-run-file FILE \
        --audience AUDIENCE \
        --document DOCUMENT \
        [--protected-entities-file FILE]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

# File extensions that indicate a file reference
_FILE_EXTENSIONS = (
    ".py", ".yaml", ".yml", ".json", ".sh", ".ini", ".toml",
    ".cfg", ".xml", ".env", ".md", ".sql",
)

# Schema-qualified name: word.word where each segment is ≥3 lowercase chars
# (catches raw_fmp.income_statements, public.stocks; excludes i.e., e.g., os.path)
_SCHEMA_QUALIFIED_RE = re.compile(r"^[a-z_][a-z0-9_]{2,}\.[a-z_][a-z0-9_]{2,}$")


def is_pattern_blocked(entity):
    """Check if entity matches a structurally ref-like pattern.

    Returns:
        (blocked, pattern) — blocked is True if the entity should not be
        dismissed; pattern describes why.
    """
    # File reference: contains / or ends with a known extension
    if "/" in entity:
        return True, "file path"
    for ext in _FILE_EXTENSIONS:
        if entity.endswith(ext):
            return True, f"file reference ({ext})"

    # Schema-qualified name: word.word with ≥3-char segments
    if _SCHEMA_QUALIFIED_RE.match(entity):
        return True, "schema-qualified name"

    return False, ""


def dismiss(
    entity,
    section,
    uncleared_file,
    dismissed_this_run_file,
    audience,
    document,
    protected_entities_file=None,
):
    """Dismiss entity from uncleared and add to dismissed-this-run.

    Returns:
        Tuple of (before_count, after_count), or None if entity is protected
        or pattern-blocked.
    """
    # Check protected list first
    if protected_entities_file:
        protected = load_json(protected_entities_file, default=[])
        protected_names = {
            e["name"] if isinstance(e, dict) else e for e in protected
        }
        if entity in protected_names:
            print(
                f"PROTECTED: {entity} — this entity was previously confirmed "
                "as ref-worthy. File a finding instead.",
                file=sys.stderr,
            )
            return None

    # Pattern guard: refuse to dismiss structurally ref-like entities
    blocked, pattern = is_pattern_blocked(entity)
    if blocked:
        print(
            f"Cannot dismiss {entity} — looks like a {pattern}. "
            "File a finding instead.",
            file=sys.stderr,
        )
        return None

    uncleared = load_json(uncleared_file, default=[])
    before_count = len(uncleared)

    # Remove ALL entries with this entity name (across all sections)
    updated = [e for e in uncleared if e["name"] != entity]
    save_json(uncleared_file, updated)
    after_count = len(updated)

    # Add to dismissed-this-run (dedup by name)
    dismissed = load_json(dismissed_this_run_file, default=[])
    existing_names = {e["name"] for e in dismissed}
    if entity not in existing_names:
        dismissed.append({
            "name": entity,
            "dismissed_in": section,
            "audience": audience,
            "document": document,
        })
        save_json(dismissed_this_run_file, dismissed)

    print(
        f"Dismissed: {entity}. Uncleared: {before_count} → {after_count}",
        file=sys.stderr,
    )
    return before_count, after_count


def main():
    parser = argparse.ArgumentParser(
        description="Dismiss an entity from uncleared into dismissed-this-run",
    )
    parser.add_argument(
        "--entity", required=True,
        help="Entity name to dismiss",
    )
    parser.add_argument(
        "--section", required=True,
        help="Section where the agent decided to dismiss",
    )
    parser.add_argument(
        "--uncleared-file", required=True,
        help="Path to uncleared entities JSON file",
    )
    parser.add_argument(
        "--dismissed-this-run-file", required=True,
        help="Path to dismissed-this-run JSON file",
    )
    parser.add_argument(
        "--audience", required=True,
        help="Audience name (e.g., devops, developer)",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document name (e.g., OPERATIONS)",
    )
    parser.add_argument(
        "--protected-entities-file",
        help="Path to protected-entities JSON file (optional)",
    )

    args = parser.parse_args()
    dismiss(
        entity=args.entity,
        section=args.section,
        uncleared_file=args.uncleared_file,
        dismissed_this_run_file=args.dismissed_this_run_file,
        audience=args.audience,
        document=args.document,
        protected_entities_file=args.protected_entities_file,
    )


if __name__ == "__main__":
    main()
