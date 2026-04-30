#!/usr/bin/env python3
"""Script-gated section iterator for prose verification.

Feeds one auditable section at a time to the verify-prose agent,
preventing read-ahead optimization that defeats section-at-a-time
auditing.

On each call:
1. Load state (or initialize on first call by reading manifest +
   filtering out no-ref sections)
2. Return the next section that has refs
3. Persist state (current index)

Usage:
    next-section.py --state-file PATH --prose-verify-dir DIR

Returns JSON to stdout:
    {"done": false, "section": "system-concepts", "file": "/.../system-concepts.json"}
    {"done": true, "sections_processed": 3, "sections_skipped": 2}
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

NO_REFS = "(no refs declared)"


def init_state(prose_verify_dir, sections_filter=None):
    """Initialize state by reading manifest and filtering no-ref sections.

    Args:
        prose_verify_dir: Path to directory containing manifest.json
            and per-section JSON files.
        sections_filter: Optional set of section paths to restrict
            iteration to.  When provided, only sections in this set
            *and* having refs are visited.

    Returns:
        State dict with sections, skipped, and index fields.
    """
    manifest_path = os.path.join(prose_verify_dir, "manifest.json")
    manifest = load_json(manifest_path)
    if manifest is None:
        print(
            f"Error: manifest not found: {manifest_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    sections = []
    skipped = []
    for slug in manifest["sections"]:
        section_file = os.path.join(prose_verify_dir, f"{slug}.json")
        section = load_json(section_file)
        if section and section.get("refs_as_text", "") != NO_REFS:
            if sections_filter is None or slug in sections_filter:
                sections.append(slug)
            else:
                skipped.append(slug)
        else:
            skipped.append(slug)

    return {"sections": sections, "skipped": skipped, "index": 0}


def main():
    parser = argparse.ArgumentParser(
        description="Script-gated section iterator for prose verification",
    )
    parser.add_argument(
        "--state-file", required=True,
        help="Path to state file (created on first call)",
    )
    parser.add_argument(
        "--prose-verify-dir", required=True,
        help="Path to directory with manifest.json and per-section JSONs",
    )
    parser.add_argument(
        "--sections-filter",
        help="Path to JSON file containing list of section paths to visit",
    )

    args = parser.parse_args()

    state = load_json(args.state_file)
    if state is None:
        sections_filter = None
        if args.sections_filter:
            if not os.path.isfile(args.sections_filter):
                print(
                    f"Error: sections filter file not found: {args.sections_filter}",
                    file=sys.stderr,
                )
                sys.exit(1)
            filter_data = load_json(args.sections_filter)
            if not isinstance(filter_data, list):
                print(
                    "Error: sections filter must be a JSON array of section paths",
                    file=sys.stderr,
                )
                sys.exit(1)
            sections_filter = set(filter_data)
        state = init_state(args.prose_verify_dir, sections_filter=sections_filter)

    sections = state["sections"]
    skipped = state.get("skipped", [])
    index = state["index"]

    if index >= len(sections):
        print(json.dumps({
            "done": True,
            "sections_processed": len(sections),
            "sections_skipped": len(skipped),
        }))
        return

    slug = sections[index]
    section_file = os.path.join(args.prose_verify_dir, f"{slug}.json")

    # Advance index for next call
    state["index"] = index + 1
    save_json(args.state_file, state)

    print(json.dumps({
        "done": False,
        "section": slug,
        "file": section_file,
    }))


if __name__ == "__main__":
    main()
