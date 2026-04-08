#!/usr/bin/env python3
"""Dismiss an entity from the uncleared list and add it to not-entities.

When the resolution agent determines an entity is not ref-worthy (e.g.,
a generic tool name, formatting artifact, or system username), this script:
1. Removes ALL entries with that entity name from the uncleared file
2. Appends the entity to the project's not-entities list (deduped)

This prevents the entity from being re-examined in subsequent waves or
future audit runs.

Usage:
    python3 dismiss-entity.py \
        --entity NAME \
        --section SECTION \
        --uncleared-file FILE \
        --not-entities-file FILE
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def dismiss(entity, section, uncleared_file, not_entities_file):
    """Dismiss entity from uncleared and add to not-entities list.

    Returns:
        Tuple of (before_count, after_count).
    """
    uncleared = load_json(uncleared_file, default=[])
    before_count = len(uncleared)

    # Remove ALL entries with this entity name (across all sections)
    updated = [e for e in uncleared if e["name"] != entity]
    save_json(uncleared_file, updated)
    after_count = len(updated)

    # Add to not-entities list (dedup)
    not_entities = load_json(not_entities_file, default=[])
    existing_names = {
        e["name"] if isinstance(e, dict) else e for e in not_entities
    }
    if entity not in existing_names:
        not_entities.append({"name": entity, "dismissed_in": section})
        save_json(not_entities_file, not_entities)

    print(
        f"Dismissed: {entity}. Uncleared: {before_count} → {after_count}",
        file=sys.stderr,
    )
    return before_count, after_count


def main():
    parser = argparse.ArgumentParser(
        description="Dismiss an entity from uncleared and add to not-entities",
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
        "--not-entities-file", required=True,
        help="Path to not-entities JSON file",
    )

    args = parser.parse_args()
    dismiss(
        entity=args.entity,
        section=args.section,
        uncleared_file=args.uncleared_file,
        not_entities_file=args.not_entities_file,
    )


if __name__ == "__main__":
    main()
