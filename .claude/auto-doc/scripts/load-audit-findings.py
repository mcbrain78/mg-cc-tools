#!/usr/bin/env python3
"""Merge and deduplicate audit findings from deterministic and prose checks.

Reads the deterministic audit findings file and any findings-prose-*.json
files from the audit directory, deduplicates by (document, section, check,
description), optionally filters out suppressed findings, and writes a
single merged array.

Usage:
    python3 load-audit-findings.py --audit-dir PATH --output PATH \
        [--suppress-file PATH]

Exit 0 always (empty findings is valid).
"""

import argparse
import glob
import json
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


def _load_suppressions(suppress_path):
    """Load suppressions, tolerating missing or malformed files.

    Returns (suppression_set, missing_count_unused_placeholder). The set
    contains (section, check, entity) tuples. On malformed JSON, emits
    a stderr warning and returns an empty set so the pipeline continues
    rather than crashing on a corrupt suppress file.
    """
    if not suppress_path or not os.path.isfile(suppress_path):
        return set()
    try:
        with open(suppress_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"Warning: suppress-file is malformed JSON, "
            f"proceeding without suppressions: {suppress_path} ({e})",
            file=sys.stderr,
        )
        return set()
    if not isinstance(entries, list):
        print(
            f"Warning: suppress-file is not a JSON array, "
            f"proceeding without suppressions: {suppress_path}",
            file=sys.stderr,
        )
        return set()
    return {
        (s.get("section"), s.get("check"), s.get("entity"))
        for s in entries
        if isinstance(s, dict)
    }


def _apply_suppressions(findings, suppress_path):
    """Filter findings against the suppression set.

    Findings missing the `entity` field pass through unfiltered with a
    one-line stderr warning per finding. Once all in-tree producers emit
    `entity`, this warning surfaces any new producer that forgets to set
    it. Phase-2 work can tighten this to a hard error.

    Args:
        findings: List of finding dicts (post-dedup).
        suppress_path: Path to the suppress JSON file (may be None or
            missing — both are no-ops).

    Returns:
        (filtered_findings, n_suppressed, n_missing_entity).
    """
    suppressions = _load_suppressions(suppress_path)
    if not suppressions:
        # Still need to count missing-entity findings for the summary,
        # even when there are no suppressions to apply.
        n_missing = sum(1 for f in findings if not f.get("entity"))
        for f in findings:
            if not f.get("entity"):
                print(
                    f"Warning: finding missing `entity` field, "
                    f"cannot match suppressions: "
                    f"{f.get('document', '?')}/"
                    f"{f.get('section', '?')} "
                    f"check={f.get('check', '?')}",
                    file=sys.stderr,
                )
        return findings, 0, n_missing

    kept = []
    n_suppressed = 0
    n_missing = 0
    for f in findings:
        entity = f.get("entity")
        if not entity:
            n_missing += 1
            print(
                f"Warning: finding missing `entity` field, "
                f"cannot match suppressions: "
                f"{f.get('document', '?')}/"
                f"{f.get('section', '?')} "
                f"check={f.get('check', '?')}",
                file=sys.stderr,
            )
            kept.append(f)
            continue
        key = (f.get("section"), f.get("check"), entity)
        if key in suppressions:
            n_suppressed += 1
            continue
        kept.append(f)
    return kept, n_suppressed, n_missing


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
    parser.add_argument(
        "--suppress-file",
        help="Optional path to suppressed-findings.json — entries with "
             "matching (section, check, entity) tuples are filtered out",
    )

    args = parser.parse_args()
    audit_dir = os.path.abspath(args.audit_dir)

    if not os.path.isdir(audit_dir):
        print(f"Warning: audit directory not found: {audit_dir}", file=sys.stderr)
        save_json(args.output, [])
        print("Merged 0 findings (audit dir missing)", file=sys.stderr)
        return

    merged = load_and_merge(audit_dir)
    filtered, n_suppressed, n_missing = _apply_suppressions(
        merged, args.suppress_file,
    )
    save_json(args.output, filtered)
    print(
        f"Merged {len(filtered)} findings "
        f"({n_suppressed} suppressed, {n_missing} missing entity)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
