#!/usr/bin/env python3
"""Sync markdown edits back to XML source document.

Splits a .md file on <!-- section: slug --> markers, matches each section
to the corresponding XML section by slug, and patches the CDATA body for
any section whose content has changed.

Usage:
    python3 sync-edits-to-xml.py --md-file PATH --xml-file PATH [--changed-only]

When --changed-only is set, outputs a JSON array of changed slugs to stdout
(for targeted ref re-extraction).

Zero external dependencies beyond lxml (used by lib/xml_doc).
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.xml_doc import (
    parse_xml_doc,
    serialize_xml_doc,
    update_section_body,
)
from lxml import etree

# Pattern matches <!-- section: some-slug --> with optional whitespace
SECTION_MARKER_RE = re.compile(r"^<!--\s*section:\s*(\S+)\s*-->", re.MULTILINE)


def split_md_on_markers(md_content):
    """Split markdown content into header + sections by <!-- section: slug --> markers.

    Args:
        md_content: Full markdown string.

    Returns:
        (header, sections) where:
        - header: Text before the first section marker (may be empty).
        - sections: List of (slug, body) tuples. body includes the marker line.
    """
    matches = list(SECTION_MARKER_RE.finditer(md_content))
    if not matches:
        return md_content, []

    header = md_content[:matches[0].start()].rstrip("\n")
    sections = []
    for i, match in enumerate(matches):
        slug = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_content)
        body = md_content[start:end].rstrip("\n")
        sections.append((slug, body))

    return header, sections


def sync(md_path, xml_path):
    """Sync markdown edits back to XML, return list of changed slugs.

    Args:
        md_path: Path to the edited markdown file.
        xml_path: Path to the XML source file.

    Returns:
        List of slugs whose body was changed.
    """
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    tree = etree.parse(xml_path)
    doc = parse_xml_doc(xml_path)

    _, md_sections = split_md_on_markers(md_content)
    md_by_slug = {slug: body for slug, body in md_sections}

    changed = []
    for section in doc["sections"]:
        slug = section["slug"]
        if slug not in md_by_slug:
            continue
        md_body = md_by_slug[slug]
        xml_body = section["body"].strip("\n")
        if md_body != xml_body:
            update_section_body(tree, slug, md_body)
            changed.append(slug)

    if changed:
        serialize_xml_doc(tree, xml_path)

    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Sync markdown edits back to XML source document"
    )
    parser.add_argument(
        "--md-file", required=True,
        help="Path to the edited markdown file",
    )
    parser.add_argument(
        "--xml-file", required=True,
        help="Path to the XML source file",
    )
    parser.add_argument(
        "--changed-only", action="store_true",
        help="Output JSON array of changed slugs to stdout",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.md_file):
        print(f"Error: markdown file not found: {args.md_file}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.xml_file):
        print(f"Error: XML file not found: {args.xml_file}", file=sys.stderr)
        sys.exit(1)

    changed = sync(args.md_file, args.xml_file)

    if args.changed_only:
        print(json.dumps(changed))

    n = len(changed)
    print(
        f"Synced {n} changed section(s) to XML",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
