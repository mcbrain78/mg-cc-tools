#!/usr/bin/env python3
"""Validate and upsert a single manifest entry to a reference manifest file.

Called by writer agents after writing each document section. The agent
writes entry data to a temp file (via Write tool), then invokes this
script with --input pointing to that file. The script validates required
fields, rejects invalid input to a .rejected file, and upserts the entry
atomically into the manifest file keyed by (document, section).

Usage:
    python3 add-manifest-entry.py \
        --input {TMP_DIR}/entry-001.json \
        --manifest .mg/docs/reference-manifests/developers.json

Input JSON must contain:
    document, section
    At least one of symbols or file_paths must be non-empty,
    unless section == "_written_sections" (metadata entry).

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

REQUIRED_FIELDS = ["document", "section"]


def validate_entry(entry):
    """Validate a single manifest entry dict.

    Returns:
        (True, None) if valid.
        (False, error_message) if invalid.
    """
    if not isinstance(entry, dict):
        return False, "Input is not a JSON object"

    for field in REQUIRED_FIELDS:
        if field not in entry:
            return False, f"Missing required field: {field}"

    # _written_sections metadata entry: requires sections_written instead
    if entry["section"] == "_written_sections":
        if "sections_written" not in entry:
            return False, "Metadata entry _written_sections requires 'sections_written' field"
        return True, None

    # Normal entry: at least one of symbols or file_paths must be non-empty
    symbols = entry.get("symbols", [])
    file_paths = entry.get("file_paths", [])
    if not symbols and not file_paths:
        return False, "At least one of 'symbols' or 'file_paths' must be non-empty"

    return True, None


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


def upsert_manifest(manifest, entry):
    """Upsert an entry into the manifest by (document, section) key.

    Args:
        manifest: The manifest dict to update in place.
        entry: The validated entry dict.

    Returns:
        The updated manifest dict.
    """
    if "documents" not in manifest:
        manifest["documents"] = {}

    doc_name = entry["document"]
    section_name = entry["section"]

    if doc_name not in manifest["documents"]:
        manifest["documents"][doc_name] = {}

    # Build the section data
    section_data = {
        "symbols": entry.get("symbols", []),
        "file_paths": entry.get("file_paths", []),
    }

    # Preserve sections_written for metadata entries
    if "sections_written" in entry:
        section_data["sections_written"] = entry["sections_written"]

    # Upsert: replaces any existing entry for this (document, section)
    manifest["documents"][doc_name][section_name] = section_data

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Validate and upsert a manifest entry"
    )
    parser.add_argument(
        "--input", required=True, dest="input_file",
        help="Path to temp file with entry JSON",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to reference manifest JSON file",
    )

    args = parser.parse_args()
    input_path = os.path.abspath(args.input_file)
    manifest_path = os.path.abspath(args.manifest)

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
    is_valid, error = validate_entry(input_data)
    if not is_valid:
        save_rejected(input_path, error)
        sys.exit(1)

    # Load existing manifest, upsert, save atomically
    manifest = load_json(manifest_path, default={})
    upsert_manifest(manifest, input_data)
    save_json(manifest_path, manifest)

    doc = input_data["document"]
    section = input_data["section"]
    print(
        f"Added manifest entry: {doc}/{section}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
