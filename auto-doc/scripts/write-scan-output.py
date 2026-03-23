#!/usr/bin/env python3
"""Validate and atomically write scan agent output.

Called by scan agents after producing complete output for one audience.
The agent writes scan data to a temp file (via Write tool), then
invokes this script with --input pointing to that file. The script
validates required fields and key format, rejects invalid input to
a .rejected file, and writes the validated output atomically.

Usage:
    python3 write-scan-output.py \
        --input .mg/docs/tmp/scan-developers.json \
        --output .mg/docs/scan-logs/scan-developers.json \
        --audience developers

Required fields in input JSON:
    source_material_index (dict with DOCUMENT/section-slug keys)
    gap_analysis (dict)

Extra fields beyond required ones are preserved in output (pass-through).

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

# Key format: DOCUMENT/section-slug
# DOCUMENT: starts with uppercase letter, followed by uppercase letters, digits, or underscores
# section-slug: lowercase alphanumeric with hyphens (consecutive hyphens allowed from
# slugified headings like "Do / Don't Rules" -> "do--dont-rules")
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+/[a-z0-9][-a-z0-9]*[a-z0-9]$")


def validate_scan_output(data):
    """Validate scan output structure.

    Checks for required fields and validates source_material_index
    key format.

    Returns:
        (True, []) if valid.
        (False, [error_messages]) if invalid.
    """
    errors = []

    if not isinstance(data, dict):
        return False, ["Input is not a JSON object"]

    if "source_material_index" not in data:
        errors.append("Missing required field: source_material_index")
    elif not isinstance(data["source_material_index"], dict):
        errors.append("source_material_index must be a dict")
    else:
        for key in data["source_material_index"]:
            if not KEY_PATTERN.match(key):
                errors.append(
                    f"Invalid key format: '{key}' "
                    f"(expected DOCUMENT/section-slug)"
                )

    if "gap_analysis" not in data:
        errors.append("Missing required field: gap_analysis")
    elif not isinstance(data["gap_analysis"], dict):
        errors.append("gap_analysis must be a dict")

    return len(errors) == 0, errors


def save_rejected(input_path, reason):
    """Save rejected input for debugging.

    Writes a JSON object with the rejection reason and the original
    input content to input_path + ".rejected".
    """
    rejected_path = input_path + ".rejected"
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        content = "<file not readable>"

    rejected = {"reason": reason, "original_input": content}
    with open(rejected_path, "w", encoding="utf-8") as f:
        json.dump(rejected, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Rejected input saved to {rejected_path}: {reason}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Validate and write scan agent output"
    )
    parser.add_argument(
        "--input", required=True, dest="input_file",
        help="Path to temp file with scan output JSON",
    )
    parser.add_argument(
        "--output", required=True,
        help="Destination path for validated output",
    )
    parser.add_argument(
        "--audience", required=True,
        help="Audience name (for logging)",
    )

    args = parser.parse_args()
    input_path = os.path.abspath(args.input_file)
    output_path = os.path.abspath(args.output)

    # Read input from temp file
    try:
        input_data = load_json(input_path)
    except json.JSONDecodeError as e:
        save_rejected(input_path, f"Invalid JSON: {e}")
        sys.exit(1)

    if input_data is None:
        save_rejected(input_path, "Input file not found or empty")
        sys.exit(1)

    # Validate
    is_valid, errors = validate_scan_output(input_data)
    if not is_valid:
        reason = "; ".join(errors)
        save_rejected(input_path, reason)
        sys.exit(1)

    # Write validated output atomically (pass through ALL fields)
    save_json(output_path, input_data)

    entry_count = len(input_data.get("source_material_index", {}))
    print(
        f"Wrote scan output for {args.audience}: "
        f"{entry_count} source material entries",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
