#!/usr/bin/env python3
"""Extract minimal verify context from docs-scan.json.

The full scan data can exceed subagent Read limits. This script
extracts only the 3 fields the verifier needs (root_path,
source_material_index, gap_analysis) into a small file.

Usage:
    python3 extract-verify-context.py \
        --scan-file .mg/docs/docs-scan.json \
        --output .mg/docs/tmp/verify-scan-context.json

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def main():
    parser = argparse.ArgumentParser(
        description="Extract verify context from scan data"
    )
    parser.add_argument(
        "--scan-file", required=True,
        help="Path to docs-scan.json",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write extracted context",
    )

    args = parser.parse_args()
    scan_path = os.path.abspath(args.scan_file)
    output_path = os.path.abspath(args.output)

    scan_data = load_json(scan_path)
    if scan_data is None:
        print(f"Error: scan file not found: {scan_path}", file=sys.stderr)
        sys.exit(1)

    context = {
        "root_path": scan_data.get("root_path", ""),
        "source_material_index": scan_data.get("source_material_index", {}),
        "gap_analysis": scan_data.get("gap_analysis", {}),
    }

    save_json(output_path, context)
    print(f"Extracted verify context to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
