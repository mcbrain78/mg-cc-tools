#!/usr/bin/env python3
"""Apply audit fixes from a fix-plan.json to XML source documents.

Reads a fix plan produced by the audit-fixer agent and applies ref and/or
body corrections to XML files. Batches multiple section fixes per XML file
into a single parse/serialize cycle.

Usage:
    python3 apply-audit-fixes.py --fix-plan PATH [--dry-run]

Exit 0 on success. Prints JSON summary to stdout.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json
from lib.xml_doc import (
    serialize_xml_doc,
    update_section_body,
    update_section_refs,
)

from lxml import etree


def collect_fixes_by_file(fix_plan):
    """Group section fixes by XML file path.

    Args:
        fix_plan: Parsed fix-plan.json dict.

    Returns:
        Dict of xml_file_path → list of section_fix dicts.
    """
    by_file = {}
    for fix_group in fix_plan.get("fixes", []):
        for section_fix in fix_group.get("section_fixes", []):
            xml_file = section_fix.get("xml_file", "")
            if not xml_file:
                continue
            if xml_file not in by_file:
                by_file[xml_file] = []
            by_file[xml_file].append(section_fix)
    return by_file


def apply_fixes(fix_plan, dry_run=False):
    """Apply all fixes from the plan to XML files.

    Args:
        fix_plan: Parsed fix-plan.json dict.
        dry_run: If True, don't write files.

    Returns:
        Summary dict with files_modified, sections_fixed, refs_fixed,
        bodies_fixed, errors.
    """
    by_file = collect_fixes_by_file(fix_plan)

    files_modified = []
    sections_fixed = 0
    refs_fixed = 0
    bodies_fixed = 0
    errors = []

    for xml_file, section_fixes in sorted(by_file.items()):
        if not os.path.isfile(xml_file):
            errors.append(f"XML file not found: {xml_file}")
            continue

        try:
            tree = etree.parse(xml_file)
        except Exception as e:
            errors.append(f"Failed to parse {xml_file}: {e}")
            continue

        file_changed = False
        for sf in section_fixes:
            slug = sf.get("slug", "")
            if not slug:
                errors.append(f"Missing slug in section fix for {xml_file}")
                continue

            try:
                if "ref_fix" in sf and sf["ref_fix"]:
                    refs = sf["ref_fix"].get("refs", [])
                    update_section_refs(tree, slug, refs)
                    refs_fixed += 1
                    file_changed = True

                if "body_fix" in sf and sf["body_fix"]:
                    body = sf["body_fix"].get("body", "")
                    update_section_body(tree, slug, body)
                    bodies_fixed += 1
                    file_changed = True

                sections_fixed += 1
            except ValueError as e:
                errors.append(f"Section fix failed for {slug} in {xml_file}: {e}")
                continue

        if file_changed:
            if not dry_run:
                serialize_xml_doc(tree, xml_file)
            files_modified.append(xml_file)

    return {
        "files_modified": files_modified,
        "sections_fixed": sections_fixed,
        "refs_fixed": refs_fixed,
        "bodies_fixed": bodies_fixed,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Apply audit fixes from fix-plan.json to XML sources"
    )
    parser.add_argument(
        "--fix-plan", required=True,
        help="Path to fix-plan.json",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would change without writing files",
    )

    args = parser.parse_args()

    plan = load_json(args.fix_plan)
    if plan is None:
        print(f"Error: fix plan not found: {args.fix_plan}", file=sys.stderr)
        sys.exit(1)

    summary = apply_fixes(plan, dry_run=args.dry_run)

    # Print summary to stdout as JSON
    print(json.dumps(summary, indent=2))

    # Human-readable to stderr
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}Applied fixes: "
        f"{summary['sections_fixed']} sections, "
        f"{summary['refs_fixed']} ref fixes, "
        f"{summary['bodies_fixed']} body fixes "
        f"across {len(summary['files_modified'])} files",
        file=sys.stderr,
    )
    if summary["errors"]:
        for err in summary["errors"]:
            print(f"  Error: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
