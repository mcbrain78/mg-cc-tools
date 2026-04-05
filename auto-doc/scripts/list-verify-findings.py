#!/usr/bin/env python3
"""Filter and query verify findings from docs-verify-findings.json.

Provides filtered views of accumulated verify findings for the generate
command and writer agents. Supports summary mode (counts by document),
filtering by document and audience, and a --clean mode that removes all
verify artifacts.

Usage:
    # Summary mode (for generate's approval UI):
    python3 list-verify-findings.py \
        --findings-file .mg/docs/docs-verify-findings.json \
        --summary \
        --output {MG_INSTALL_TMP_DIR}/findings-summary.json

    # Filter by document and audience (for writer agents):
    python3 list-verify-findings.py \
        --findings-file .mg/docs/docs-verify-findings.json \
        --document OPERATIONS --audience devops \
        --output {MG_INSTALL_TMP_DIR}/findings-ops.json

    # Clean all verify artifacts:
    python3 list-verify-findings.py \
        --clean \
        --findings-file .mg/docs/docs-verify-findings.json

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

# Verify artifacts relative to the docs directory (parent of findings file).
_VERIFY_ARTIFACTS = [
    "docs-verify-findings.json",
    "docs-verify-report.md",
    "scan-logs/verify-refs-broken.json",
    "scan-logs/verify-refs-symbols.json",
    "scan-logs/verify-refs.json",  # old format, may linger
    "docs-verify-findings-mechanical.json",
    "docs-verify-findings-editorial.json",
    # Fact-checker findings files (verify pipeline restructure)
    "docs-verify-findings-code-example.json",
    "docs-verify-findings-data-model.json",
    "docs-verify-findings-cross-doc.json",
    "docs-verify-findings-completeness.json",
]


def clean_verify_artifacts(docs_dir):
    """Remove all verify artifacts from the workspace.

    Args:
        docs_dir: The docs directory (parent of findings file).

    Removes static artifacts and dynamic per-document editorial files
    (docs-verify-findings-editorial-*.json).
    """
    for rel_path in _VERIFY_ARTIFACTS:
        full_path = os.path.join(docs_dir, rel_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            print(f"Removed: {full_path}", file=sys.stderr)

    # Dynamic cleanup: per-document editorial findings files
    for fname in os.listdir(docs_dir):
        if fname.startswith("docs-verify-findings-editorial-") and fname.endswith(".json"):
            full_path = os.path.join(docs_dir, fname)
            os.remove(full_path)
            print(f"Removed: {full_path}", file=sys.stderr)


def filter_findings(findings, document=None, audience=None):
    """Filter findings by optional criteria.

    Args:
        findings: List of finding dicts.
        document: If set, include only findings for this document.
        audience: If set, include only findings for this audience.

    Returns:
        Filtered list of finding dicts.
    """
    result = findings

    if document:
        result = [f for f in result if f.get("document") == document]

    if audience:
        result = [f for f in result if f.get("audience") == audience]

    return result


def build_summary(findings):
    """Build summary dict with counts by document.

    Returns:
        Dict with keys: total, by_document, distinct_groups.
    """
    summary = {
        "total": len(findings),
        "by_document": {},
    }

    groups = set()
    for f in findings:
        doc = f.get("document", "unknown")
        summary["by_document"][doc] = summary["by_document"].get(doc, 0) + 1
        gid = f.get("group_id", f"{doc}/{f.get('section', '')}")
        groups.add(gid)

    summary["distinct_groups"] = len(groups)

    return summary


def build_grouped(findings):
    """Group findings by group_id for the approval UI.

    Returns:
        List of group dicts, sorted by count descending then group_id.
        Each group contains:
        - group_id, document, section, count
        - representative: the first finding in the group
        - findings: all findings in the group
    """
    groups = {}
    for f in findings:
        gid = f.get("group_id", f"{f.get('document', '')}/{f.get('section', '')}")
        if gid not in groups:
            groups[gid] = []
        groups[gid].append(f)

    result = []
    for gid, group_findings in groups.items():
        representative = group_findings[0]
        result.append({
            "group_id": gid,
            "document": representative.get("document", ""),
            "section": representative.get("section", ""),
            "count": len(group_findings),
            "representative": representative,
            "findings": group_findings,
        })

    # Sort by count descending, then group_id alphabetically
    result.sort(key=lambda g: (-g["count"], g["group_id"]))

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Filter and query verify findings"
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to docs-verify-findings.json",
    )
    parser.add_argument(
        "--output", default=None,
        help="Path to write results (required unless --clean)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove all verify artifacts and exit",
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Create an empty [] findings file and exit",
    )
    parser.add_argument(
        "--merge-from", action="append", default=[],
        help="Path to agent-specific findings file to merge (repeatable)",
    )
    parser.add_argument(
        "--merge-glob", action="append", default=[],
        help="Glob pattern for findings files to merge (repeatable)",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Produce summary counts instead of filtered list",
    )
    parser.add_argument(
        "--grouped", action="store_true",
        help="Group findings by group_id for approval UI display",
    )
    parser.add_argument(
        "--document", default=None,
        help="Filter by document name (e.g., OPERATIONS)",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Filter by audience (e.g., devops)",
    )
    args = parser.parse_args()
    findings_path = os.path.abspath(args.findings_file)
    docs_dir = os.path.dirname(findings_path)

    # --clean mode: remove verify artifacts and exit
    if args.clean:
        clean_verify_artifacts(docs_dir)
        return

    # --init mode: create empty findings file and exit
    if args.init:
        save_json(findings_path, [])
        print(f"Initialized empty findings: {findings_path}", file=sys.stderr)
        return

    # --output is required for non-init/clean modes
    has_merge = args.merge_from or args.merge_glob
    if not args.output and not has_merge:
        parser.error("--output is required unless --clean or --init is used")

    output_path = os.path.abspath(args.output) if args.output else None

    # Load findings -- treat missing file as empty array
    findings = load_json(findings_path, default=[])

    # --merge-from / --merge-glob: load and append findings
    if has_merge:
        merge_paths = [os.path.abspath(p) for p in args.merge_from]
        for pattern in args.merge_glob:
            merge_paths.extend(sorted(glob.glob(pattern)))
        for merge_path in merge_paths:
            merge_path = os.path.abspath(merge_path)
            agent_findings = load_json(merge_path, default=[])
            findings.extend(agent_findings)
        save_json(findings_path, findings)

    if not output_path:
        return

    # Apply filters (even in summary mode, filters apply first)
    filtered = filter_findings(
        findings,
        document=args.document,
        audience=args.audience,
    )

    # Build output
    if args.summary:
        result = build_summary(filtered)
    elif args.grouped:
        result = build_grouped(filtered)
    else:
        result = filtered

    save_json(output_path, result)


if __name__ == "__main__":
    main()
