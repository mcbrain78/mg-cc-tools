#!/usr/bin/env python3
"""Sync markdown edits back to XML source document.

Splits a .md file on <!-- section: slug --> markers, matches each section
to the corresponding XML section by path, and patches the CDATA body for
any section whose content has changed.

Tree hierarchy is reconstructed from heading levels after the flat marker
split: ## = top-level, ### = child, #### = grandchild, etc.

Usage:
    python3 sync-edits-to-xml.py --md-file PATH --xml-file PATH [--changed-only]

When --changed-only is set, outputs a JSON array of changed paths to stdout
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
    walk_sections,
)
from lxml import etree

# Pattern matches <!-- section: some-slug --> with optional whitespace
SECTION_MARKER_RE = re.compile(r"^<!--\s*section:\s*(\S+)\s*-->", re.MULTILINE)

# Heading level regex: ## = 2, ### = 3, #### = 4, etc.
HEADING_RE = re.compile(r"^(#{2,6})\s+", re.MULTILINE)


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


def _heading_depth(body):
    """Extract heading depth from body (## = 2, ### = 3, etc.).

    Returns 2 (top-level) if no heading found.
    """
    m = HEADING_RE.search(body)
    if m:
        return len(m.group(1))
    return 2  # default to top-level if no heading found


def _infer_paths(md_sections):
    """Infer slash-separated paths from (slug, body) tuples using heading levels.

    Uses a stack-based algorithm: stack tracks [(depth, slug)] ancestor chain.
    For each section: pop stack while top's depth >= current depth, build path
    from remaining stack slugs + current slug joined by "/", push current.

    Args:
        md_sections: List of (slug, body) tuples from split_md_on_markers.

    Returns:
        List of (path, slug, body) tuples with full slash-separated paths.
    """
    stack = []  # [(depth, slug)] -- tracks ancestor chain
    result = []

    for slug, body in md_sections:
        depth = _heading_depth(body)

        # Pop stack to find parent: any heading same-or-shallower pops
        while stack and stack[-1][0] >= depth:
            stack.pop()

        # Build path from remaining stack + current slug
        path = "/".join(s for _, s in stack) + ("/" if stack else "") + slug

        result.append((path, slug, body))
        stack.append((depth, slug))

    return result


def sync(md_path, xml_path):
    """Sync markdown edits back to XML, return list of changed paths.

    Args:
        md_path: Path to the edited markdown file.
        xml_path: Path to the XML source file.

    Returns:
        List of slash-separated paths whose body was changed.
    """
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    tree = etree.parse(xml_path)
    doc = parse_xml_doc(xml_path)

    _, md_sections = split_md_on_markers(md_content)
    inferred = _infer_paths(md_sections)
    md_by_path = {path: body for path, slug, body in inferred}

    changed = []
    for xml_path_key, section in walk_sections(doc["sections"]):
        if xml_path_key not in md_by_path:
            continue
        md_body = md_by_path[xml_path_key]
        xml_body = section["body"].strip("\n")
        if md_body != xml_body:
            update_section_body(tree, xml_path_key, md_body)
            changed.append(xml_path_key)

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
        help="Output JSON array of changed paths to stdout",
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
