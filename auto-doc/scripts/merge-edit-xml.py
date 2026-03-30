#!/usr/bin/env python3
"""Merge edited sections from an edit XML file back into master XMLs.

Reads an edit XML file produced by extract-edit-xml.py (and modified by
the fixer agent), compares each section's body and refs against the
current master, and writes changes back.

Usage:
    python3 merge-edit-xml.py --edit-file PATH

Prints JSON summary to stdout. Exit 0 always.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.xml_doc import (
    _parse_refs,
    serialize_xml_doc,
    update_section_body,
    update_section_refs,
)

from lxml import etree


def merge_edit_xml(edit_file):
    """Merge edited sections back into master XML files.

    Args:
        edit_file: Path to the edit XML file.

    Returns:
        Summary dict with files_modified, sections_updated, errors.
    """
    tree = etree.parse(edit_file)
    root = tree.getroot()

    files_modified = []
    sections_updated = 0
    errors = []

    # Cache master trees — multiple sections may target the same file
    master_cache = {}  # source_path -> (tree, changed)

    for section_el in root.findall("section"):
        source = section_el.get("source", "")
        slug = section_el.get("slug", "")

        if not source or not slug:
            errors.append("Section missing source or slug attribute")
            continue

        if not os.path.isfile(source):
            errors.append(f"Master XML not found: {source}")
            continue

        # Parse master (cached)
        if source not in master_cache:
            try:
                master_cache[source] = (etree.parse(source), False)
            except Exception as e:
                errors.append(f"Failed to parse {source}: {e}")
                continue

        master_tree, was_changed = master_cache[source]

        # Find master section
        master_section = None
        for el in master_tree.getroot().findall("section"):
            if el.get("slug") == slug:
                master_section = el
                break

        if master_section is None:
            errors.append(f"Section '{slug}' not found in {source}")
            continue

        # Extract edit body
        edit_body_el = section_el.find("body")
        edit_body = (edit_body_el.text or "") if edit_body_el is not None else ""

        # Extract edit refs (flat format via _parse_refs)
        edit_refs_el = section_el.find("refs")
        edit_refs = _parse_refs(edit_refs_el) if edit_refs_el is not None else []

        # Get current master values
        master_body_el = master_section.find("body")
        master_body = (
            (master_body_el.text or "") if master_body_el is not None else ""
        )

        master_refs_el = master_section.find("refs")
        master_refs = (
            _parse_refs(master_refs_el) if master_refs_el is not None else []
        )

        changed = False

        if edit_body != master_body:
            update_section_body(master_tree, slug, edit_body)
            changed = True

        if edit_refs != master_refs:
            update_section_refs(master_tree, slug, edit_refs)
            changed = True

        if changed:
            sections_updated += 1
            master_cache[source] = (master_tree, True)

    # Serialize changed masters
    for source, (mtree, was_changed) in master_cache.items():
        if was_changed:
            serialize_xml_doc(mtree, source)
            files_modified.append(source)

    return {
        "files_modified": files_modified,
        "sections_updated": sections_updated,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Merge edited sections back into master XML files",
    )
    parser.add_argument("--edit-file", required=True)

    args = parser.parse_args()

    if not os.path.isfile(args.edit_file):
        print(json.dumps({
            "files_modified": [],
            "sections_updated": 0,
            "errors": [f"Edit file not found: {args.edit_file}"],
        }))
        print(
            f"Error: edit file not found: {args.edit_file}", file=sys.stderr,
        )
        return

    summary = merge_edit_xml(args.edit_file)

    print(json.dumps(summary, indent=2))

    print(
        f"Merged {summary['sections_updated']} sections "
        f"into {len(summary['files_modified'])} files",
        file=sys.stderr,
    )
    if summary["errors"]:
        for err in summary["errors"]:
            print(f"  Error: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
