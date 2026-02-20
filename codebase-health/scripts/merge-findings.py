#!/usr/bin/env python3
"""Merge per-category scan JSON files into final health-scan-findings.json.

Called by the scanner orchestrator after all subagents complete. Reads
per-category JSON arrays, assigns sequential IDs, deduplicates, computes
summary counts, and writes the final findings file.

Usage:
    python3 merge-findings.py \
        --scan-dir <project-root>/.health-scan/scan-logs \
        --output <project-root>/.health-scan/health-scan-findings.json \
        --project "project-name" \
        --root-path "/absolute/path/to/project"

Atomic writes via temp file + os.replace(). Zero external dependencies.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone


def load_json(path):
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Atomic write JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def should_skip(filename):
    """Return True if this file should NOT be merged (WIP, orientation, verify, raw, non-scan)."""
    base = os.path.basename(filename)
    # Only process scan-*.json files
    if not base.startswith("scan-"):
        return True
    if not base.endswith(".json"):
        return True
    # Skip WIP checkpoint files
    if "-wip.json" in base:
        return True
    # Skip raw script output files
    if "-raw.json" in base:
        return True
    # Skip orientation (it's markdown in .md but guard against .json variant)
    if "orientation" in base:
        return True
    # Skip verify files
    if base.startswith("scan-verify") or "verify" in base:
        return True
    return False


def deduplicate(findings):
    """Deduplicate by (file, lines tuple, category). Keeps first occurrence."""
    seen = set()
    result = []
    dups = 0
    for f in findings:
        loc = f.get("location", {})
        key = (
            loc.get("file", ""),
            tuple(loc.get("lines", [])),
            f.get("category", ""),
        )
        if key in seen:
            dups += 1
            continue
        seen.add(key)
        result.append(f)
    return result, dups


def assign_ids(findings):
    """Assign sequential IDs: F001, F002, ... (zero-padded)."""
    n = len(findings)
    if n >= 1000:
        width = len(str(n))
    else:
        width = 3
    for i, f in enumerate(findings, start=1):
        f["id"] = f"F{i:0{width}d}"


def compute_summary(findings):
    """Compute summary counts."""
    summary = {
        "total_findings": len(findings),
        "by_severity": {},
        "by_category": {},
    }
    for f in findings:
        sev = f.get("severity", "unknown")
        cat = f.get("category", "unknown")
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
        summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-category scan JSON files into final findings"
    )
    parser.add_argument(
        "--scan-dir", required=True,
        help="Path to scan-logs directory containing scan-*.json files"
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write health-scan-findings.json"
    )
    parser.add_argument(
        "--project", required=True,
        help="Project name"
    )
    parser.add_argument(
        "--root-path", required=True,
        help="Absolute path to project root"
    )

    args = parser.parse_args()

    scan_dir = os.path.abspath(args.scan_dir)
    if not os.path.isdir(scan_dir):
        print(f"Error: scan directory not found: {scan_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect all scan-*.json files
    pattern = os.path.join(scan_dir, "scan-*.json")
    json_files = sorted(glob.glob(pattern))

    all_findings = []
    categories_seen = set()

    for json_file in json_files:
        if should_skip(json_file):
            continue

        try:
            data = load_json(json_file)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: skipping {json_file}: {e}", file=sys.stderr)
            continue

        if not isinstance(data, list):
            print(f"Warning: skipping {json_file}: not a JSON array",
                  file=sys.stderr)
            continue

        # Extract category name from filename for tracking
        base = os.path.basename(json_file)
        cat_match = re.match(r"scan-(.+)\.json$", base)
        if cat_match:
            categories_seen.add(cat_match.group(1))

        all_findings.extend(data)

    # Deduplicate
    findings, dups = deduplicate(all_findings)

    # Add verification and implementation placeholders
    for f in findings:
        f["verification"] = None
        f["implementation"] = None

    # Assign IDs
    assign_ids(findings)

    # Build output
    output = {
        "project": args.project,
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "root_path": args.root_path,
        "summary": compute_summary(findings),
        "findings": findings,
    }

    # Write
    output_path = os.path.abspath(args.output)
    save_json(output_path, output)

    print(f"Merged {len(findings)} findings from {len(categories_seen)} "
          f"categories ({dups} duplicates removed)", file=sys.stderr)


if __name__ == "__main__":
    main()
