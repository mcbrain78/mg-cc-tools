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
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.xml_doc import (
    _build_refs_xml,
    _find_section_by_path,
    _parse_refs,
    serialize_xml_doc,
    update_section_body,
    update_section_refs,
)

from lxml import etree


def _strip_formatting_whitespace(el):
    """Remove whitespace-only text/tail so pretty_print controls formatting.

    When lxml parses existing XML, inter-element whitespace is stored as
    .text/.tail properties.  A freshly built element has none.  Stripping
    these before serializing makes both produce identical pretty_print output.
    """
    if el.text and not el.text.strip():
        el.text = None
    if el.tail and not el.tail.strip():
        el.tail = None
    for child in el:
        _strip_formatting_whitespace(child)


def _normalize_refs_xml(refs_el):
    """Serialize a <refs> element with normalized whitespace."""
    el = deepcopy(refs_el)
    _strip_formatting_whitespace(el)
    return etree.tostring(el, encoding="unicode", pretty_print=True).strip()


def _is_refs_canonical(refs_el):
    """Check whether a <refs> element is in canonical form.

    Parses to flat dicts, rebuilds, and compares serialized output.
    Normalizes parsed whitespace before comparison so elements read
    from disk compare equal to freshly built elements.
    Empty refs are always canonical.
    """
    if refs_el is None or len(refs_el) == 0:
        return True
    original = _normalize_refs_xml(refs_el)
    canonical_el = etree.Element("refs")
    _build_refs_xml(canonical_el, _parse_refs(refs_el))
    canonical = _normalize_refs_xml(canonical_el)
    return original == canonical


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
        # Path is primary key; fall back to slug for backward compat
        path = section_el.get("path") or section_el.get("slug", "")

        if not source or not path:
            errors.append("Section missing source or path/slug attribute")
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

        # Find master section via path-based navigation
        master_section = _find_section_by_path(master_tree.getroot(), path)

        if master_section is None:
            errors.append(f"Section '{path}' not found in {source}")
            continue

        # Extract edit body
        edit_body_el = section_el.find("body")
        edit_body = (edit_body_el.text or "") if edit_body_el is not None else ""

        # Extract edit refs (flat format via _parse_refs)
        edit_refs_el = section_el.find("refs")
        edit_refs = _parse_refs(edit_refs_el) if edit_refs_el is not None else []

        # Tamper check: if agent edited refs directly (non-canonical),
        # skip ref changes and warn. Body changes still apply.
        refs_tampered = not _is_refs_canonical(edit_refs_el)
        if refs_tampered:
            print(
                f"Warning: <refs> in section '{path}' was modified directly "
                f"(not via update-fix-refs.py). "
                f"Ignoring ref changes for this section.",
                file=sys.stderr,
            )

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
            update_section_body(master_tree, path, edit_body)
            changed = True

        if not refs_tampered and edit_refs != master_refs:
            update_section_refs(master_tree, path, edit_refs)
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
