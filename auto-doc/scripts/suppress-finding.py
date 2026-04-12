#!/usr/bin/env python3
"""Add a suppression entry so a known false-positive finding is skipped.

Usage:
    python3 suppress-finding.py \
        --suppress-file PATH \
        --section SECTION \
        --check CHECK \
        --entity ENTITY

The suppress file stores a JSON array of {section, check, entity} tuples.
An exact match on all three fields means "this specific finding is a known
non-issue" and will be silently skipped by add-verify-finding.py.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def suppress(suppress_file, section, check, entity):
    """Add a suppression entry (deduped by all three fields).

    Returns:
        True if entry was added, False if already present.
    """
    entries = load_json(suppress_file, default=[])

    for e in entries:
        if (e.get("section") == section
                and e.get("check") == check
                and e.get("entity") == entity):
            print(
                f"Already suppressed: {section} / {check} / {entity}",
                file=sys.stderr,
            )
            return False

    entries.append({
        "section": section,
        "check": check,
        "entity": entity,
    })
    save_json(suppress_file, entries)
    print(
        f"Suppressed: {section} / {check} / {entity}",
        file=sys.stderr,
    )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Add a suppression entry for a known false-positive finding",
    )
    parser.add_argument(
        "--suppress-file", required=True,
        help="Path to suppressed-findings.json",
    )
    parser.add_argument(
        "--section", required=True,
        help="Section path (e.g., monitoring-alerting/etl-run-logging)",
    )
    parser.add_argument(
        "--check", required=True,
        help="Check type (e.g., dangling-prose-reference)",
    )
    parser.add_argument(
        "--entity", required=True,
        help="Entity name to suppress",
    )

    args = parser.parse_args()
    suppress(
        suppress_file=args.suppress_file,
        section=args.section,
        check=args.check,
        entity=args.entity,
    )


if __name__ == "__main__":
    main()
