#!/usr/bin/env python3
"""Merge and deduplicate audit findings from deterministic and prose checks.

Reads the deterministic audit findings file and any findings-prose-*.json
files from the audit directory, deduplicates by (document, section, check,
description), and writes a single merged array.

Usage:
    python3 load-audit-findings.py --audit-dir PATH --output PATH

Exit 0 always (empty findings is valid).
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def load_and_merge(audit_dir):
    """Load and merge all audit findings from audit_dir.

    Args:
        audit_dir: Path to the audit directory containing findings files.

    Returns:
        Deduplicated list of finding dicts.
    """
    all_findings = []

    # Deterministic findings
    det_path = os.path.join(audit_dir, "findings-refs.json")
    det_findings = load_json(det_path, default=[])
    all_findings.extend(det_findings)

    # Prose findings (one file per document)
    prose_pattern = os.path.join(audit_dir, "findings-prose-*.json")
    for prose_path in sorted(glob.glob(prose_pattern)):
        prose_findings = load_json(prose_path, default=[])
        all_findings.extend(prose_findings)

    return deduplicate(all_findings)


def deduplicate(findings):
    """Remove duplicate findings by (document, section, check, description).

    Args:
        findings: List of finding dicts.

    Returns:
        Deduplicated list preserving first-seen order.
    """
    seen = set()
    result = []
    for f in findings:
        key = (
            f.get("document", ""),
            f.get("section", ""),
            f.get("check", ""),
            f.get("description", ""),
        )
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Merge and deduplicate audit findings"
    )
    parser.add_argument(
        "--audit-dir", required=True,
        help="Path to the audit directory with findings files",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the merged findings JSON",
    )

    args = parser.parse_args()
    audit_dir = os.path.abspath(args.audit_dir)

    if not os.path.isdir(audit_dir):
        print(f"Warning: audit directory not found: {audit_dir}", file=sys.stderr)
        save_json(args.output, [])
        print("Merged 0 findings (audit dir missing)", file=sys.stderr)
        return

    merged = load_and_merge(audit_dir)
    save_json(args.output, merged)
    print(f"Merged {len(merged)} findings", file=sys.stderr)


if __name__ == "__main__":
    main()
