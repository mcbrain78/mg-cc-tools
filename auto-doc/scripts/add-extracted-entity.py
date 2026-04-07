#!/usr/bin/env python3
"""Append an extracted entity to an entities JSON file.

Deduplicates by (name, section) pair.  Follows the add-verify-finding.py
inline-mode CLI pattern.

Usage:
    python3 add-extracted-entity.py \
        --entities-file FILE --name NAME --section SECTION
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def main():
    parser = argparse.ArgumentParser(
        description="Append an extracted entity to an entities file",
    )
    parser.add_argument(
        "--entities-file", required=True,
        help="Path to entities JSON file",
    )
    parser.add_argument("--name", required=True, help="Entity name")
    parser.add_argument("--section", required=True, help="Section path")

    args = parser.parse_args()
    entities_path = os.path.abspath(args.entities_file)

    entities = load_json(entities_path, default=[])

    # Dedup by (name, section)
    for e in entities:
        if e["name"] == args.name and e["section"] == args.section:
            print(
                f"Skipped duplicate: {args.name} in {args.section}",
                file=sys.stderr,
            )
            return

    entities.append({"name": args.name, "section": args.section})
    save_json(entities_path, entities)
    print(f"Added entity: {args.name} in {args.section}", file=sys.stderr)


if __name__ == "__main__":
    main()
