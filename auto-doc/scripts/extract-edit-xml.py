#!/usr/bin/env python3
"""Extract per-group edit XML from master XML sources.

Takes LLM-produced grouping JSON + merged findings + xml-dir and produces
a focused edit XML file containing only the sections relevant to one group.
The fixer agent edits this file directly using the Edit tool.

Usage:
    python3 extract-edit-xml.py \
        --grouping-file PATH \
        --group-index N \
        --findings-file PATH \
        --xml-dir PATH \
        --output PATH

Exit 0 always (0 sections is valid).
"""

import argparse
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json

from lxml import etree


# ---------------------------------------------------------------------------
# XML index (reused logic from former load-xml-context.py)
# ---------------------------------------------------------------------------

def _build_xml_index(xml_dir):
    """Build a map of (audience, document) -> xml_path from xml_dir.

    Handles both audience subdirs (e.g., xml-sources/devops/OPS.xml) and
    root-level files (e.g., xml-sources/GLOSSARY.xml).
    """
    index = {}
    if not os.path.isdir(xml_dir):
        return index

    for dirpath, _dirnames, filenames in os.walk(xml_dir):
        for fname in filenames:
            if not fname.endswith(".xml"):
                continue
            xml_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(xml_path, xml_dir)
            parts = rel.replace("\\", "/").split("/")
            doc_name = os.path.splitext(parts[-1])[0]
            audience = parts[0] if len(parts) > 1 else "all"
            index[(audience, doc_name)] = xml_path

    return index


def _find_xml_for_finding(finding, xml_index):
    """Find the XML path for a finding, trying audience and 'all'."""
    audience = finding.get("audience", "")
    document = finding.get("document", "")

    key = (audience, document)
    if key in xml_index:
        return xml_index[key]

    key = ("all", document)
    if key in xml_index:
        return xml_index[key]

    return None


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_edit_xml(grouping, findings, xml_dir, group_index):
    """Extract one group's sections into an edit XML tree.

    Args:
        grouping: Dict with "groups" list from LLM grouping agent.
        findings: Full list of finding dicts.
        xml_dir: Path to xml-sources directory.
        group_index: Which group to extract (0-based).

    Returns:
        lxml.etree._ElementTree for the edit XML.

    Raises:
        ValueError: If group_index is out of range.
    """
    groups = grouping.get("groups", [])
    if group_index < 0 or group_index >= len(groups):
        raise ValueError(
            f"Group index {group_index} out of range (0-{len(groups) - 1})"
        )

    group = groups[group_index]
    group_id = group.get("group_id", "unknown")
    summary = group.get("root_cause_summary", "")

    # Resolve finding indices
    indices = group.get("finding_indices", [])
    group_findings = [findings[i] for i in indices if 0 <= i < len(findings)]

    # Build XML index
    xml_index = _build_xml_index(xml_dir)

    # Group findings by (xml_path, slug)
    sections_map = {}
    for f in group_findings:
        xml_path = _find_xml_for_finding(f, xml_index)
        if not xml_path:
            continue
        slug = f.get("section", "")
        key = (xml_path, slug)
        if key not in sections_map:
            sections_map[key] = {
                "xml_path": xml_path,
                "slug": slug,
                "document": f.get("document", ""),
                "audience": f.get("audience", ""),
                "findings": [],
            }
        sections_map[key]["findings"].append(f)

    # Build edit XML
    root = etree.Element("edit-group", id=group_id)
    summary_el = etree.SubElement(root, "summary")
    summary_el.text = summary

    parsed_cache = {}
    for info in sections_map.values():
        xml_path = info["xml_path"]
        slug = info["slug"]

        # Parse master XML (cached)
        if xml_path not in parsed_cache:
            try:
                parsed_cache[xml_path] = etree.parse(xml_path)
            except Exception:
                continue
        master_tree = parsed_cache[xml_path]

        # Find section in master
        section_el = None
        for el in master_tree.getroot().findall("section"):
            if el.get("slug") == slug:
                section_el = el
                break
        if section_el is None:
            continue

        # Create edit section
        edit_section = etree.SubElement(
            root, "section",
            source=xml_path,
            slug=slug,
            audience=info["audience"],
            document=info["document"],
        )

        # Add findings (read-only context)
        findings_el = etree.SubElement(edit_section, "findings")
        for f in info["findings"]:
            finding_el = etree.SubElement(
                findings_el, "finding", check=f.get("check", ""),
            )
            finding_el.text = f.get("description", "")

        # Copy refs from master (deep copy preserves native XML structure)
        master_refs = section_el.find("refs")
        if master_refs is not None:
            edit_section.append(deepcopy(master_refs))
        else:
            etree.SubElement(edit_section, "refs")

        # Copy body from master (CDATA for human-readable editing)
        master_body = section_el.find("body")
        body_el = etree.SubElement(edit_section, "body")
        if master_body is not None and master_body.text:
            body_el.text = etree.CDATA(master_body.text)
        else:
            body_el.text = etree.CDATA("")

    return etree.ElementTree(root)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract per-group edit XML from master XML sources",
    )
    parser.add_argument("--grouping-file", required=True)
    parser.add_argument("--group-index", required=True, type=int)
    parser.add_argument("--findings-file", required=True)
    parser.add_argument("--xml-dir", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    grouping = load_json(args.grouping_file, default={"groups": []})
    findings = load_json(args.findings_file, default=[])

    tree = extract_edit_xml(
        grouping, findings, os.path.abspath(args.xml_dir), args.group_index,
    )

    # Count sections
    section_count = len(tree.getroot().findall("section"))

    # Atomic write
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    tmp = args.output + ".tmp"
    tree.write(tmp, xml_declaration=True, encoding="utf-8", pretty_print=True)
    os.replace(tmp, args.output)

    print(
        f"Extracted {section_count} sections for group {args.group_index}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
