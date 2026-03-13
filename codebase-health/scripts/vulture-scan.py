#!/usr/bin/env python3
"""Cross-file dead code detection via vulture for codebase-health pipeline.

Scans for unused functions, classes, imports, and variables using vulture's
Python API. Low min-confidence (60%) captures more candidates; the LLM agent
filters false positives by checking for dynamic dispatch.

Usage:
    python3 vulture-scan.py --root <path> --output <path> [--ignore-file <path>] [--min-confidence 60]

Requires: pip install vulture
"""

import argparse
import json
import os
import sys
from collections import defaultdict

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ignore import load_ignore_patterns, should_ignore

try:
    from vulture import Vulture
except ImportError:
    print(
        "Error: vulture is not installed.\n"
        "Install it with: pip install vulture",
        file=sys.stderr,
    )
    sys.exit(1)


def scan(root, ignore_file=None, min_confidence=60):
    """Run vulture scan on the project root.

    Returns structured JSON-serializable dict.
    """
    patterns = load_ignore_patterns(ignore_file)

    v = Vulture(min_confidence=min_confidence)
    v.scavenge([root])

    unused_code = []
    by_type = defaultdict(int)
    by_confidence = defaultdict(int)

    for item in v.get_unused_code():
        rel_path = os.path.relpath(item.filename, root)

        # Skip ignored files
        if should_ignore(item.filename, patterns, root):
            continue

        entry = {
            "file": rel_path,
            "first_lineno": item.first_lineno,
            "last_lineno": item.last_lineno,
            "type": item.typ,
            "name": item.name,
            "confidence": item.confidence,
            "size": item.size,
        }
        unused_code.append(entry)
        by_type[item.typ] += 1
        by_confidence[str(item.confidence)] += 1

    return {
        "summary": {
            "total_items": len(unused_code),
            "by_type": dict(by_type),
            "by_confidence": dict(by_confidence),
        },
        "unused_code": unused_code,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Cross-file dead code detection via vulture"
    )
    parser.add_argument("--root", required=True, help="Project root directory")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument(
        "--ignore-file", default=None, help="Path to .health-ignore file"
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=60,
        help="Minimum confidence threshold (default: 60)",
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Auto-detect .health-ignore if not specified
    if args.ignore_file is None:
        default_ignore = os.path.join(root, ".mg", "health-scan", ".health-ignore")
        if os.path.isfile(default_ignore):
            args.ignore_file = default_ignore

    result = scan(root, args.ignore_file, args.min_confidence)

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Print summary to stderr
    summary = result["summary"]
    print(
        f"Found {summary['total_items']} unused code items",
        file=sys.stderr,
    )
    if summary["by_type"]:
        parts = [f"{v} {k}" for k, v in sorted(summary["by_type"].items())]
        print(f"  By type: {', '.join(parts)}", file=sys.stderr)


if __name__ == "__main__":
    main()
