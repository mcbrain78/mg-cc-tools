#!/usr/bin/env python3
"""Load XML context for pre-grouped audit findings.

Takes LLM-produced grouping JSON + merged findings + xml-dir and produces
fix-context.json with full XML section bodies for the fixer agent.

Usage:
    python3 load-xml-context.py \
        --grouping-file PATH \
        --findings-file PATH \
        --xml-dir PATH \
        --output PATH

Exit 0 always (empty groups is valid).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json
from lib.xml_doc import parse_xml_doc


# ---------------------------------------------------------------------------
# XML context loading
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

    # Try exact match
    key = (audience, document)
    if key in xml_index:
        return xml_index[key]

    # Try root level
    key = ("all", document)
    if key in xml_index:
        return xml_index[key]

    return None


def load_xml_context(group_findings, xml_index, parsed_cache):
    """Load affected XML sections for a group of findings.

    Args:
        group_findings: List of finding dicts in the same root-cause group.
        xml_index: Map of (audience, document) -> xml_path.
        parsed_cache: Dict of xml_path -> parsed doc dict (shared cache).

    Returns:
        List of affected_section dicts with xml_file, audience, document,
        slug, current_refs, current_body.
    """
    affected = []
    seen = set()

    for f in group_findings:
        xml_path = _find_xml_for_finding(f, xml_index)
        if not xml_path:
            continue

        slug = f.get("section", "")
        key = (xml_path, slug)
        if key in seen:
            continue
        seen.add(key)

        # Parse XML (cached)
        if xml_path not in parsed_cache:
            try:
                parsed_cache[xml_path] = parse_xml_doc(xml_path)
            except Exception:
                continue

        doc = parsed_cache[xml_path]
        for section in doc["sections"]:
            if section["slug"] == slug:
                affected.append({
                    "xml_file": xml_path,
                    "audience": doc["audience"],
                    "document": f.get("document", ""),
                    "slug": slug,
                    "current_refs": section["refs"],
                    "current_body": section["body"],
                })
                break

    return affected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_fix_context(grouping, findings, xml_dir):
    """Resolve LLM grouping into fix-context with XML sections.

    Args:
        grouping: Dict with "groups" list from LLM grouping agent.
            Each group has group_id, root_cause_summary, finding_indices.
        findings: Full list of finding dicts (indexed by finding_indices).
        xml_dir: Path to xml-sources directory.

    Returns:
        Dict with "groups", "total_findings", "total_groups".
    """
    xml_index = _build_xml_index(xml_dir)
    parsed_cache = {}

    groups = grouping.get("groups", [])
    result_groups = []

    for group in groups:
        indices = group.get("finding_indices", [])
        group_findings_list = []
        for idx in indices:
            if 0 <= idx < len(findings):
                group_findings_list.append(findings[idx])

        sections = load_xml_context(group_findings_list, xml_index, parsed_cache)

        result_groups.append({
            "group_id": group.get("group_id", "unknown"),
            "root_cause_summary": group.get("root_cause_summary", ""),
            "findings": group_findings_list,
            "affected_sections": sections,
        })

    return {
        "groups": result_groups,
        "total_findings": len(findings),
        "total_groups": len(result_groups),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Load XML context for pre-grouped audit findings"
    )
    parser.add_argument(
        "--grouping-file", required=True,
        help="Path to LLM grouping JSON (group_id, root_cause_summary, finding_indices)",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to merged findings JSON array",
    )
    parser.add_argument(
        "--xml-dir", required=True,
        help="Path to xml-sources directory",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write fix-context JSON",
    )

    args = parser.parse_args()

    grouping = load_json(args.grouping_file, default={"groups": []})
    findings = load_json(args.findings_file, default=[])

    if not grouping.get("groups"):
        save_json(args.output, {
            "groups": [],
            "total_findings": len(findings),
            "total_groups": 0,
        })
        print("No groups to process", file=sys.stderr)
        return

    result = build_fix_context(grouping, findings, os.path.abspath(args.xml_dir))
    save_json(args.output, result)
    print(
        f"Loaded XML context for {result['total_groups']} groups "
        f"({result['total_findings']} findings)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
