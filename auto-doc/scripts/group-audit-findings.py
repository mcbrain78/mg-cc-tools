#!/usr/bin/env python3
"""Group audit findings by root cause and load XML context for each group.

Reads merged findings, groups them by shared entity mentions or identical
descriptions, then loads the affected XML sections for each group so the
fixer agent has full context.

Usage:
    python3 group-audit-findings.py \
        --findings-file PATH \
        --xml-dir PATH \
        --output PATH

Exit 0 always (empty findings is valid).
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json
from lib.xml_doc import parse_xml_doc


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

# Patterns to extract entity mentions from finding descriptions.
# Matches backtick-quoted identifiers and common code patterns.
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_DOTTED_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b")  # CamelCase


def extract_entities(description):
    """Extract entity mentions from a finding description.

    Looks for backtick-quoted names (most common in findings) and
    CamelCase class names.

    Args:
        description: Finding description string.

    Returns:
        Frozenset of entity strings found.
    """
    entities = set()

    # Backtick-quoted names (e.g., `etl_runs`, `compute_finance_metrics`)
    for match in _BACKTICK_RE.finditer(description):
        entity = match.group(1).strip()
        # Skip long phrases and common non-entity text
        if entity and len(entity) < 80 and " " not in entity:
            entities.add(entity)

    # CamelCase class names not already captured
    for match in _DOTTED_NAME_RE.finditer(description):
        entities.add(match.group(1))

    return frozenset(entities)


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def group_findings(findings):
    """Group findings by root cause.

    Strategy:
    1. Extract entity mentions from each finding's description.
    2. Findings sharing any entity → same group (union-find).
    3. Identical descriptions → same group (fallback).
    4. Remaining → singleton groups.

    Args:
        findings: List of finding dicts.

    Returns:
        List of groups, each a list of finding dicts.
    """
    n = len(findings)
    if n == 0:
        return []

    # Extract entities for each finding
    entities_per = [extract_entities(f.get("description", "")) for f in findings]

    # Union-find for grouping
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Group by shared entities
    # Build entity → finding indices map
    entity_to_indices = {}
    for i, ents in enumerate(entities_per):
        for e in ents:
            if e not in entity_to_indices:
                entity_to_indices[e] = []
            entity_to_indices[e].append(i)

    for indices in entity_to_indices.values():
        for j in range(1, len(indices)):
            union(indices[0], indices[j])

    # Group by identical descriptions (fallback for findings with no entities)
    desc_to_indices = {}
    for i, f in enumerate(findings):
        if not entities_per[i]:
            desc = f.get("description", "")
            if desc not in desc_to_indices:
                desc_to_indices[desc] = []
            desc_to_indices[desc].append(i)

    for indices in desc_to_indices.values():
        for j in range(1, len(indices)):
            union(indices[0], indices[j])

    # Collect groups
    groups_map = {}
    for i in range(n):
        root = find(i)
        if root not in groups_map:
            groups_map[root] = []
        groups_map[root].append(findings[i])

    return list(groups_map.values())


def make_group_id(group):
    """Generate a group_id from the group's findings.

    Uses the most common entity mention + a summary of the check types.
    """
    # Collect all entities across the group
    all_entities = set()
    checks = set()
    for f in group:
        all_entities.update(extract_entities(f.get("description", "")))
        checks.add(f.get("check", "unknown"))

    # Pick the most descriptive entity (longest, as a heuristic)
    if all_entities:
        primary = max(all_entities, key=len)
    else:
        # Fall back to document + section from first finding
        first = group[0]
        primary = first.get("document", "unknown") + "-" + first.get("section", "unknown")

    check_str = "-".join(sorted(checks))
    return f"{primary}-{check_str}"


def summarize_group(group):
    """Generate a human-readable root cause summary for a group."""
    all_entities = set()
    for f in group:
        all_entities.update(extract_entities(f.get("description", "")))

    entity_str = ", ".join(sorted(all_entities)[:5]) if all_entities else "unknown"
    n = len(group)
    docs = {f.get("document", "") for f in group}
    sections = {f.get("section", "") for f in group}

    return (
        f"{n} finding(s) related to {entity_str} "
        f"across {len(sections)} section(s) in {len(docs)} document(s)"
    )


# ---------------------------------------------------------------------------
# XML context loading
# ---------------------------------------------------------------------------

def _build_xml_index(xml_dir):
    """Build a map of (audience, document) → xml_path from xml_dir.

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


def load_xml_context(group, xml_index, _parsed_cache):
    """Load affected XML sections for a group of findings.

    Args:
        group: List of finding dicts in the same root-cause group.
        xml_index: Map of (audience, document) → xml_path.
        _parsed_cache: Dict of xml_path → parsed doc dict (shared cache).

    Returns:
        List of affected_section dicts with xml_file, audience, document,
        slug, current_refs, current_body.
    """
    affected = []
    seen = set()

    for f in group:
        xml_path = _find_xml_for_finding(f, xml_index)
        if not xml_path:
            continue

        slug = f.get("section", "")
        key = (xml_path, slug)
        if key in seen:
            continue
        seen.add(key)

        # Parse XML (cached)
        if xml_path not in _parsed_cache:
            try:
                _parsed_cache[xml_path] = parse_xml_doc(xml_path)
            except Exception:
                continue

        doc = _parsed_cache[xml_path]
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

def build_groups(findings, xml_dir):
    """Group findings and load XML context for each group.

    Args:
        findings: List of finding dicts.
        xml_dir: Path to xml-sources directory.

    Returns:
        Dict with "groups", "total_findings", "total_groups".
    """
    xml_index = _build_xml_index(xml_dir)
    parsed_cache = {}

    raw_groups = group_findings(findings)

    result_groups = []
    for group in raw_groups:
        group_id = make_group_id(group)
        summary = summarize_group(group)
        sections = load_xml_context(group, xml_index, parsed_cache)

        result_groups.append({
            "group_id": group_id,
            "root_cause_summary": summary,
            "findings": group,
            "affected_sections": sections,
        })

    return {
        "groups": result_groups,
        "total_findings": len(findings),
        "total_groups": len(result_groups),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Group audit findings by root cause with XML context"
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to merged findings JSON",
    )
    parser.add_argument(
        "--xml-dir", required=True,
        help="Path to xml-sources directory",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write grouped findings JSON",
    )

    args = parser.parse_args()

    findings = load_json(args.findings_file, default=[])
    if not findings:
        save_json(args.output, {
            "groups": [],
            "total_findings": 0,
            "total_groups": 0,
        })
        print("No findings to group", file=sys.stderr)
        return

    result = build_groups(findings, os.path.abspath(args.xml_dir))
    save_json(args.output, result)
    print(
        f"Grouped {result['total_findings']} findings into "
        f"{result['total_groups']} groups",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
