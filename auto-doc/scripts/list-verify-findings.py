#!/usr/bin/env python3
"""Filter and query verify findings from docs-verify-findings.json.

Provides filtered views of accumulated verify findings for the generate
command and writer agents. Supports summary mode (counts by severity
and document), filtering by document, audience, and minimum severity,
and a --clean mode that removes all verify artifacts.

Usage:
    # Summary mode (for generate's approval UI):
    python3 list-verify-findings.py \
        --findings-file .mg/docs/docs-verify-findings.json \
        --summary \
        --output {TMP_DIR}/findings-summary.json

    # Filter by document and audience (for writer agents):
    python3 list-verify-findings.py \
        --findings-file .mg/docs/docs-verify-findings.json \
        --document OPERATIONS --audience devops \
        --output {TMP_DIR}/findings-ops.json

    # Filter by minimum severity:
    python3 list-verify-findings.py \
        --findings-file .mg/docs/docs-verify-findings.json \
        --severity high \
        --output {TMP_DIR}/findings-high.json

    # Clean all verify artifacts:
    python3 list-verify-findings.py \
        --clean \
        --findings-file .mg/docs/docs-verify-findings.json

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

# Index 0 = most severe. Used for "at or above" severity filtering.
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

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


def filter_findings(findings, document=None, audience=None, severity=None):
    """Filter findings by optional criteria.

    Args:
        findings: List of finding dicts.
        document: If set, include only findings for this document.
        audience: If set, include only findings for this audience.
        severity: If set, include findings at or above this severity
            level (rank-based, not exact match).

    Returns:
        Filtered list of finding dicts.
    """
    result = findings

    if document:
        result = [f for f in result if f.get("document") == document]

    if audience:
        result = [f for f in result if f.get("audience") == audience]

    if severity:
        min_rank = SEVERITY_ORDER.index(severity)
        result = [
            f for f in result
            if f.get("severity") in SEVERITY_ORDER
            and SEVERITY_ORDER.index(f["severity"]) <= min_rank
        ]

    return result


def build_summary(findings):
    """Build summary dict with counts by severity and document.

    Returns:
        Dict with keys: total, by_severity, by_document.
    """
    summary = {
        "total": len(findings),
        "by_severity": {},
        "by_document": {},
    }

    groups = set()
    for f in findings:
        sev = f.get("severity", "unknown")
        doc = f.get("document", "unknown")
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
        summary["by_document"][doc] = summary["by_document"].get(doc, 0) + 1
        gid = f.get("group_id", f"{doc}/{f.get('section', '')}")
        groups.add(gid)

    summary["distinct_groups"] = len(groups)

    return summary


def build_grouped(findings):
    """Group findings by group_id for the approval UI.

    Returns:
        List of group dicts, sorted by highest severity then group_id.
        Each group contains:
        - group_id, document, section, count, highest_severity
        - representative: the highest-severity finding in the group
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
        # Pick highest severity as representative
        best = min(
            group_findings,
            key=lambda x: SEVERITY_ORDER.index(x.get("severity", "info")),
        )
        result.append({
            "group_id": gid,
            "document": best.get("document", ""),
            "section": best.get("section", ""),
            "count": len(group_findings),
            "highest_severity": best.get("severity", "info"),
            "representative": best,
            "findings": group_findings,
        })

    # Sort by severity (most severe first), then group_id
    result.sort(key=lambda g: (
        SEVERITY_ORDER.index(g["highest_severity"]),
        g["group_id"],
    ))

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
    parser.add_argument(
        "--severity", default=None,
        help="Filter by minimum severity (includes this level and above)",
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
    if not args.output and not args.merge_from:
        parser.error("--output is required unless --clean or --init is used")

    output_path = os.path.abspath(args.output)

    # Load findings -- treat missing file as empty array
    findings = load_json(findings_path, default=[])

    # --merge-from: load and append findings from agent-specific files
    if args.merge_from:
        for merge_path in args.merge_from:
            merge_path = os.path.abspath(merge_path)
            agent_findings = load_json(merge_path, default=[])
            findings.extend(agent_findings)
        save_json(findings_path, findings)

    if not args.output:
        return

    # Apply filters (even in summary mode, filters apply first)
    filtered = filter_findings(
        findings,
        document=args.document,
        audience=args.audience,
        severity=args.severity,
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
