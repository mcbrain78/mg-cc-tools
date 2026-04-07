#!/usr/bin/env python3
"""Propagate a dangling-prose-reference finding to all other sections.

After the resolution agent files a finding for an entity in one section,
this script:
1. Finds all other sections in the uncleared file with the same entity
2. Files identical findings for each via add-verify-finding.py
3. Removes ALL entries for the entity from the uncleared file

This ensures consistent judgment: if `prefect` needs a ref in section 3,
it needs a ref everywhere it appears.

Usage:
    python3 propagate-finding.py \
        --entity NAME \
        --section SECTION \
        --findings-file FILE \
        --uncleared-file FILE \
        --document DOC \
        --audience AUD \
        --suggestion TEXT
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

ADD_FINDING_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "add-verify-finding.py",
)


def propagate(entity, section, findings_file, uncleared_file,
              document, audience, suggestion):
    """Propagate finding to other sections and remove entity from uncleared.

    Returns:
        Tuple of (propagated_count, before_count, after_count).
    """
    uncleared = load_json(uncleared_file, default=[])
    before_count = len(uncleared)

    # Find other sections with the same entity (deduplicate, preserve order)
    other_sections = list(dict.fromkeys(
        e["section"] for e in uncleared
        if e["name"] == entity and e["section"] != section
    ))

    # Propagate finding to each other section
    for target_section in other_sections:
        subprocess.run(
            [
                sys.executable, ADD_FINDING_SCRIPT,
                "--findings-file", findings_file,
                "--document", document,
                "--section", target_section,
                "--audience", audience,
                "--check", "dangling-prose-reference",
                "--description",
                f"Prose mentions `{entity}` which is not covered by any "
                f"declared ref (propagated from {section})",
                "--suggestion", suggestion,
            ],
            capture_output=True, text=True,
        )

    # Remove ALL entries for this entity from uncleared
    updated = [e for e in uncleared if e["name"] != entity]
    save_json(uncleared_file, updated)
    after_count = len(updated)

    propagated_count = len(other_sections)
    print(
        f"Propagated: {entity} → {propagated_count} sections. "
        f"Uncleared: {before_count} → {after_count}",
        file=sys.stderr,
    )
    return propagated_count, before_count, after_count


def main():
    parser = argparse.ArgumentParser(
        description="Propagate a finding to all sections with the same entity",
    )
    parser.add_argument(
        "--entity", required=True,
        help="Entity name to propagate",
    )
    parser.add_argument(
        "--section", required=True,
        help="Section where the finding was originally filed",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to findings JSON file",
    )
    parser.add_argument(
        "--uncleared-file", required=True,
        help="Path to uncleared entities JSON file",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document name",
    )
    parser.add_argument(
        "--audience", required=True,
        help="Audience name",
    )
    parser.add_argument(
        "--suggestion", required=True,
        help="Suggested fix text",
    )

    args = parser.parse_args()
    propagate(
        entity=args.entity,
        section=args.section,
        findings_file=args.findings_file,
        uncleared_file=args.uncleared_file,
        document=args.document,
        audience=args.audience,
        suggestion=args.suggestion,
    )


if __name__ == "__main__":
    main()
