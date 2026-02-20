#!/usr/bin/env python3
"""Record a single finding to a per-category JSON array file.

Called by scanner subagents to append one finding at a time, replacing
manual JSON construction by the LLM.

Usage:
    python3 add-finding.py \
        --output <scan-logs/scan-orphaned-code.json> \
        --category orphaned-code \
        --severity high \
        --confidence high \
        --title "Orphaned tool implementation legacy_search" \
        --file "tools/legacy_search.py" \
        --lines 1,85 \
        --symbol "legacy_search" \
        --evidence "No file imports from tools/legacy_search.py..." \
        --recommendation remove \
        [--notes "Optional caveats"]

Atomic writes via temp file + os.replace(). Zero external dependencies.
"""

import argparse
import json
import os
import sys

VALID_CATEGORIES = [
    "orphaned-code",
    "stale-code",
    "dead-code-path",
    "redundant-logic",
    "unused-dependency",
    "contract-drift",
    "dangling-config",
    "circular-dependency",
]

VALID_SEVERITIES = ["critical", "high", "medium", "low"]
VALID_CONFIDENCES = ["high", "medium", "low"]
VALID_RECOMMENDATIONS = ["remove", "refactor", "update", "merge", "investigate"]


def load_array(path):
    """Load a JSON array from path, or return [] if file doesn't exist."""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"Error: {path} does not contain a JSON array", file=sys.stderr)
        sys.exit(1)
    return data


def save_array(path, data):
    """Atomic write: write to .tmp then replace."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def parse_lines(lines_str):
    """Parse 'start,end' into [start, end] integers."""
    parts = lines_str.split(",")
    if len(parts) != 2:
        print(f"Error: --lines must be 'start,end', got '{lines_str}'",
              file=sys.stderr)
        sys.exit(1)
    try:
        return [int(parts[0].strip()), int(parts[1].strip())]
    except ValueError:
        print(f"Error: --lines values must be integers, got '{lines_str}'",
              file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Record a single finding to a per-category JSON array file"
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to the per-category JSON array file"
    )
    parser.add_argument(
        "--category", required=True, choices=VALID_CATEGORIES,
        help="Finding category slug"
    )
    parser.add_argument(
        "--severity", required=True, choices=VALID_SEVERITIES,
        help="Finding severity"
    )
    parser.add_argument(
        "--confidence", required=True, choices=VALID_CONFIDENCES,
        help="Finding confidence level"
    )
    parser.add_argument(
        "--title", required=True,
        help="Short description of the finding"
    )
    parser.add_argument(
        "--file", required=True, dest="finding_file",
        help="Relative path to the file containing the finding"
    )
    parser.add_argument(
        "--lines", required=True,
        help="Line range as 'start,end' (comma-separated)"
    )
    parser.add_argument(
        "--symbol", default=None,
        help="Function or class name (optional, defaults to null)"
    )
    parser.add_argument(
        "--evidence", required=True,
        help="What was observed and why it's a finding"
    )
    parser.add_argument(
        "--recommendation", required=True, choices=VALID_RECOMMENDATIONS,
        help="Recommended action"
    )
    parser.add_argument(
        "--notes", default="",
        help="Caveats or additional context (optional, defaults to empty string)"
    )

    args = parser.parse_args()

    # Parse line range
    lines = parse_lines(args.lines)

    # Build finding object (no id, no verification, no implementation)
    finding = {
        "category": args.category,
        "severity": args.severity,
        "confidence": args.confidence,
        "title": args.title,
        "location": {
            "file": args.finding_file,
            "lines": lines,
            "symbol": args.symbol,
        },
        "evidence": args.evidence,
        "recommendation": args.recommendation,
        "notes": args.notes,
    }

    # Load existing array, append, save
    output_path = os.path.abspath(args.output)
    findings = load_array(output_path)
    findings.append(finding)
    save_array(output_path, findings)

    print(f"Added finding: {args.title} ({args.category}, {args.severity})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
