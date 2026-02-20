#!/usr/bin/env python3
"""Split verified findings into downstream documents.

Generates two outputs from health-scan-findings.json:

1. GSD bootstrap markdown (needs-review findings grouped by category)
   for feeding into gsd:plan-phase as planning context.

2. Implementor queue JSON (safe-to-fix findings only)
   for the implementor to read instead of the full findings file.

Usage:
    python3 split-findings.py \
        --findings <path>/health-scan-findings.json \
        --bootstrap-out <path>/health-verify-gsd-bootstrap.md \
        --implementor-out <path>/health-implement-queue.json \
        [--test-baseline <path>/health-verify-test-baseline.json]

Zero external dependencies — stdlib only.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def load_json(path):
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Atomic write JSON."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def save_text(path, text):
    """Atomic write text."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def filter_findings(findings, safety_value):
    """Return findings matching a verification.safety value."""
    result = []
    for f in findings:
        v = f.get("verification")
        if v and v.get("safety") == safety_value:
            result.append(f)
    return result


def group_by_category(findings):
    """Group findings by category, preserving order of first appearance."""
    groups = {}
    order = []
    for f in findings:
        cat = f.get("category", "unknown")
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(f)
    return [(cat, groups[cat]) for cat in order]


def estimate_effort(finding):
    """Estimate effort based on dependent count and file touches."""
    v = finding.get("verification", {}) or {}
    deps = v.get("dependents", []) or []
    n = len(deps)
    if n <= 1:
        return "Small"
    elif n <= 4:
        return "Medium"
    else:
        return "Large"


def format_finding_entry(finding):
    """Format a single finding for the bootstrap markdown."""
    v = finding.get("verification", {}) or {}
    loc = finding.get("location", {}) or {}

    lines = []
    fid = finding.get("id", "?")
    title = finding.get("title", "")
    lines.append(f"### {fid} — {title}")

    # Severity and category
    severity = finding.get("severity", "?").upper()
    category = finding.get("category", "?")
    file_ref = loc.get("file", "?")
    loc_lines = loc.get("lines")
    if loc_lines:
        file_ref += ":" + ",".join(str(l) for l in loc_lines)
    lines.append(f"- **Severity:** {severity} | **Category:** {category}")
    lines.append(f"- **File:** `{file_ref}`")

    # Problem — combine evidence + verification reasoning
    evidence = finding.get("evidence", "")
    reasoning = v.get("reasoning", "")
    if evidence and reasoning:
        lines.append(f"- **Problem:** {evidence}")
    elif evidence:
        lines.append(f"- **Problem:** {evidence}")
    elif reasoning:
        lines.append(f"- **Problem:** {reasoning}")

    # Impact analysis as runtime impact if present
    impact = v.get("impact_analysis", "")
    if impact:
        lines.append(f"- **Runtime impact:** {impact}")

    # Proposed fix
    proposed = v.get("proposed_change", "")
    if proposed:
        lines.append(f"- **Proposed fix:** {proposed}")

    # Files touched (dependents)
    deps = v.get("dependents", []) or []
    if deps:
        lines.append(f"- **Files touched:** {', '.join('`' + d + '`' for d in deps)}")

    # Test coverage
    test_cov = v.get("test_coverage", "")
    if test_cov:
        lines.append(f"- **Test coverage:** {test_cov}")

    # Risk
    risk = v.get("risk_notes", "")
    if risk:
        lines.append(f"- **Risk:** {risk}")

    return "\n".join(lines)


def generate_bootstrap(data, needs_review, test_baseline):
    """Generate the GSD bootstrap markdown document."""
    lines = []

    # Header
    scan_date = data.get("scan_date", datetime.now(timezone.utc).isoformat())
    lines.append("# Needs-Review Findings — Codebase Health Verification")
    lines.append("")
    lines.append(f"**Source:** `.health-scan/health-scan-findings.json` (verified {scan_date[:10]})")
    lines.append("**Purpose:** Context document for GSD phase planning. Each finding has been "
                 "verified by a dedicated agent and classified as `needs-review` — meaning the "
                 "fix is likely correct but has uncertainty, touches multiple files, or affects "
                 "critical paths. All require human approval before implementation.")

    # Test baseline
    if test_baseline:
        passed = test_baseline.get("passed", "?")
        skipped = test_baseline.get("skipped", 0)
        failed = test_baseline.get("failed", 0)
        lines.append("")
        parts = [f"{passed} passed"]
        if skipped:
            parts.append(f"{skipped} skipped")
        parts.append(f"{failed} failed")
        lines.append(f"**Test baseline:** {', '.join(parts)}")

    lines.append("")
    lines.append("---")

    # Group findings by category
    grouped = group_by_category(needs_review)

    group_num = 0
    group_summaries = []
    for cat, findings in grouped:
        group_num += 1
        # Determine group theme from category
        theme = cat.replace("-", " ").title()
        finding_ids = [f.get("id", "?") for f in findings]

        # Estimate group effort from max of individual efforts
        efforts = [estimate_effort(f) for f in findings]
        if "Large" in efforts:
            group_effort = "Large"
        elif "Medium" in efforts:
            group_effort = "Medium"
        else:
            group_effort = "Small"

        group_summaries.append({
            "name": theme,
            "ids": finding_ids,
            "effort": group_effort,
        })

        lines.append("")
        lines.append(f"## Group {group_num}: {theme}")
        lines.append("")
        for finding in findings:
            lines.append(format_finding_entry(finding))
            lines.append("")
            lines.append("---")

    # Implementation Grouping Suggestion table
    lines.append("")
    lines.append("## Implementation Grouping Suggestion")
    lines.append("")
    lines.append("For phase planning, these naturally cluster into work units:")
    lines.append("")
    lines.append("| Group | Findings | Theme | Effort |")
    lines.append("|---|---|---|---|")
    for gs in group_summaries:
        ids_str = ", ".join(gs["ids"])
        lines.append(f"| {gs['name']} | {ids_str} | {gs['name']} | {gs['effort']} |")

    lines.append("")
    return "\n".join(lines)


def generate_implementor_queue(data, safe_findings):
    """Generate the implementor queue JSON (same structure, filtered findings)."""
    queue = {
        "project": data.get("project", ""),
        "scan_date": data.get("scan_date", ""),
        "root_path": data.get("root_path", ""),
        "summary": {
            "total_findings": len(safe_findings),
            "by_severity": {},
            "by_category": {},
        },
        "findings": safe_findings,
    }

    # Recompute summary counts
    for f in safe_findings:
        sev = f.get("severity", "unknown")
        cat = f.get("category", "unknown")
        queue["summary"]["by_severity"][sev] = (
            queue["summary"]["by_severity"].get(sev, 0) + 1
        )
        queue["summary"]["by_category"][cat] = (
            queue["summary"]["by_category"].get(cat, 0) + 1
        )

    return queue


def main():
    parser = argparse.ArgumentParser(
        description="Split verified findings into GSD bootstrap and implementor queue"
    )
    parser.add_argument(
        "--findings", required=True, help="Path to health-scan-findings.json"
    )
    parser.add_argument(
        "--bootstrap-out", required=True,
        help="Output path for GSD bootstrap markdown"
    )
    parser.add_argument(
        "--implementor-out", required=True,
        help="Output path for implementor queue JSON"
    )
    parser.add_argument(
        "--test-baseline", default=None,
        help="Path to health-verify-test-baseline.json (optional)"
    )
    args = parser.parse_args()

    # Load findings
    findings_path = os.path.abspath(args.findings)
    if not os.path.isfile(findings_path):
        print(f"Error: findings file not found: {findings_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = load_json(findings_path)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: failed to load findings: {e}", file=sys.stderr)
        sys.exit(1)

    all_findings = data.get("findings", [])

    # Load test baseline if provided
    test_baseline = None
    if args.test_baseline:
        baseline_path = os.path.abspath(args.test_baseline)
        if os.path.isfile(baseline_path):
            try:
                test_baseline = load_json(baseline_path)
            except (json.JSONDecodeError, OSError):
                print(f"Warning: could not load test baseline: {baseline_path}",
                      file=sys.stderr)

    # Split findings
    needs_review = filter_findings(all_findings, "needs-review")
    safe_to_fix = filter_findings(all_findings, "safe-to-fix")

    # Generate bootstrap (only if needs-review findings exist)
    bootstrap_path = os.path.abspath(args.bootstrap_out)
    if needs_review:
        os.makedirs(os.path.dirname(bootstrap_path), exist_ok=True)
        bootstrap_md = generate_bootstrap(data, needs_review, test_baseline)
        save_text(bootstrap_path, bootstrap_md)
        print(f"Bootstrap: {len(needs_review)} needs-review findings → {bootstrap_path}",
              file=sys.stderr)
    else:
        print("Bootstrap: no needs-review findings, skipping", file=sys.stderr)

    # Generate implementor queue (only if safe-to-fix findings exist)
    impl_path = os.path.abspath(args.implementor_out)
    if safe_to_fix:
        os.makedirs(os.path.dirname(impl_path), exist_ok=True)
        queue = generate_implementor_queue(data, safe_to_fix)
        save_json(impl_path, queue)
        print(f"Implementor queue: {len(safe_to_fix)} safe-to-fix findings → {impl_path}",
              file=sys.stderr)
    else:
        print("Implementor queue: no safe-to-fix findings, skipping", file=sys.stderr)

    # Summary
    do_not_touch = filter_findings(all_findings, "do-not-touch")
    unverified = [f for f in all_findings
                  if not f.get("verification") or not f["verification"].get("safety")]
    print(f"\nSplit summary: {len(safe_to_fix)} safe-to-fix, "
          f"{len(needs_review)} needs-review, "
          f"{len(do_not_touch)} do-not-touch, "
          f"{len(unverified)} unverified",
          file=sys.stderr)


if __name__ == "__main__":
    main()
