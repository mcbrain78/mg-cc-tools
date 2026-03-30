#!/usr/bin/env python3
"""Deterministic check: do declared refs appear in section prose?

For each XML source document, checks whether each declared ref's name
appears somewhere in the section body text. Refs that are declared but
never mentioned in the prose are flagged as reference-integrity findings.

Usage:
    python3 check-ref-prose-coverage.py \
        --xml-dir PATH \
        --findings-file PATH \
        [--audience FILTER] \
        [--min-name-length N]

Appends findings to --findings-file atomically. Exit 0 always
(findings are data, not errors).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json
from lib.xml_doc import parse_xml_doc


# ---------------------------------------------------------------------------
# Name extraction per ref type
# ---------------------------------------------------------------------------

# Minimum name length to avoid false matches on short identifiers like "id"
DEFAULT_MIN_NAME_LENGTH = 3


def _ref_check_items(ref):
    """Extract check items for a ref.

    Returns a list of (alternatives, label) tuples. Each tuple represents
    one concept to verify: `alternatives` is a list of strings (any match
    counts as covered), and `label` is the human-readable description.

    For example, a config ref returns one item with [full_path, basename]
    as alternatives. A db ref with a column returns two separate items
    (one for the table, one for the column).
    """
    ref_type = ref.get("type", "")

    if ref_type == "code":
        name = ref.get("name", "")
        kind = ref.get("kind", "")
        if name:
            return [([name], f"{kind} `{name}`")]

    elif ref_type == "db":
        items = []
        table = ref.get("table", "")
        column = ref.get("column")
        schema = ref.get("schema", "")
        if table:
            label = f"table `{schema}.{table}`" if schema else f"table `{table}`"
            items.append(([table], label))
        if column:
            items.append(([column], f"column `{column}`"))
        return items

    elif ref_type == "flow":
        name = ref.get("name", "")
        if name:
            return [([name], f"flow `{name}`")]

    elif ref_type == "env":
        name = ref.get("name", "")
        if name:
            return [([name], f"env var `{name}`")]

    elif ref_type == "config":
        path = ref.get("path", "")
        if path:
            basename = os.path.basename(path)
            alts = [path]
            if basename != path:
                alts.append(basename)
            return [(alts, f"config `{path}`")]

    elif ref_type == "enum":
        cls = ref.get("class", "")
        if cls:
            return [([cls], f"enum `{cls}`")]

    return []


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------

def check_section_coverage(section, doc_name, audience, min_name_length):
    """Check whether declared refs appear in section body.

    Args:
        section: Parsed section dict with "slug", "body", "refs".
        doc_name: Document name (filename without extension).
        audience: Document audience string.
        min_name_length: Skip ref names shorter than this.

    Returns:
        List of finding dicts for refs not found in body.
    """
    body = section.get("body", "")
    slug = section.get("slug", "")
    refs = section.get("refs", [])

    if not body or not refs:
        return []

    findings = []
    # Track which labels we've already checked to avoid duplicate findings
    # (e.g., same table name from multiple column refs)
    checked_labels = set()

    for ref in refs:
        for alternatives, label in _ref_check_items(ref):
            if label in checked_labels:
                continue
            checked_labels.add(label)

            # Filter to names long enough to check
            eligible = [n for n in alternatives if len(n) >= min_name_length]
            if not eligible:
                continue

            # Covered if ANY alternative appears in body
            if any(name in body for name in eligible):
                continue

            findings.append({
                "document": doc_name,
                "section": slug,
                "audience": audience,
                "check": "reference-integrity",
                "description": (
                    f"Declared ref {label} is not mentioned in the section prose"
                ),
                "suggestion": (
                    "Either remove the ref (if it's an implementation detail "
                    "not relevant to this section) or mention it in the prose"
                ),
            })

    return findings


def check_xml_file(xml_path, min_name_length):
    """Check ref-prose coverage for all sections in an XML document.

    Returns list of finding dicts.
    """
    doc = parse_xml_doc(xml_path)
    audience = doc["audience"]
    doc_name = os.path.splitext(os.path.basename(xml_path))[0]

    findings = []
    for section in doc["sections"]:
        findings.extend(
            check_section_coverage(section, doc_name, audience, min_name_length)
        )

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Check whether declared refs appear in section prose"
    )
    parser.add_argument(
        "--xml-dir", required=True,
        help="Path to xml-sources directory",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to findings JSON file to append results to",
    )
    parser.add_argument(
        "--audience",
        help="Audience filter (e.g., 'devops') — only check matching XML files",
    )
    parser.add_argument(
        "--min-name-length", type=int, default=DEFAULT_MIN_NAME_LENGTH,
        help=f"Skip ref names shorter than N chars (default: {DEFAULT_MIN_NAME_LENGTH})",
    )

    args = parser.parse_args()
    xml_dir = os.path.abspath(args.xml_dir)

    if not os.path.isdir(xml_dir):
        print(f"Error: xml-dir not found: {xml_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect XML files
    xml_files = []
    for dirpath, _dirnames, filenames in os.walk(xml_dir):
        for fname in sorted(filenames):
            if not fname.endswith(".xml"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), xml_dir)
            parts = rel.replace("\\", "/").split("/")
            audience = parts[0] if len(parts) > 1 else None

            if args.audience and audience and audience != args.audience:
                continue

            xml_files.append(os.path.join(dirpath, fname))

    # Run checks
    all_findings = []
    total_refs = 0
    for xml_path in xml_files:
        doc_name = os.path.splitext(os.path.basename(xml_path))[0]
        findings = check_xml_file(xml_path, args.min_name_length)
        all_findings.extend(findings)

        doc = parse_xml_doc(xml_path)
        for section in doc["sections"]:
            total_refs += len(section.get("refs", []))

        print(
            f"  {doc_name}: {total_refs} refs checked, "
            f"{len(findings)} coverage gaps",
            file=sys.stderr,
        )

    # Append to findings file
    existing = load_json(args.findings_file, default=[])
    existing.extend(all_findings)
    save_json(args.findings_file, existing)

    print(
        f"Ref-prose coverage: {total_refs} refs checked, "
        f"{len(all_findings)} findings",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
