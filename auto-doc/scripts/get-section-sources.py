#!/usr/bin/env python3
"""Fetch source_files for a single section from docs-scan.json.

Writers call this per-section to avoid loading the full scan into context.
Prints JSON to stdout: {"source_files": [...]} plus synthesized_from if present.

Usage:
    python3 get-section-sources.py \
        --scan-file .mg/docs/docs-scan.json \
        --key "ARCHITECTURE/data-acquisition"
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json


def main():
    parser = argparse.ArgumentParser(
        description="Fetch source_files for a single section from docs-scan.json"
    )
    parser.add_argument(
        "--scan-file", required=True, help="Path to docs-scan.json"
    )
    parser.add_argument(
        "--key", required=True, help="Section key (e.g. ARCHITECTURE/data-acquisition)"
    )
    args = parser.parse_args()

    scan_path = os.path.abspath(args.scan_file)
    data = load_json(scan_path)
    if data is None:
        print(f"Error: scan file not found: {scan_path}", file=sys.stderr)
        sys.exit(1)

    index = data.get("source_material_index", {})
    if args.key not in index:
        print(f"Error: key not found: {args.key}", file=sys.stderr)
        sys.exit(1)

    entry = index[args.key]
    result = {"source_files": entry.get("source_files", [])}
    if "synthesized_from" in entry:
        result["synthesized_from"] = entry["synthesized_from"]

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
