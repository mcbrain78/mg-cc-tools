#!/usr/bin/env python3
"""Validate and upsert manifest entries to a reference manifest file.

Called by writer agents after writing document sections. The agent
writes entry data to temp files (via Write tool), then invokes this
script with --input pointing to each file. Multiple --input flags
can be passed to batch entries in a single call.

Usage:
    python3 add-manifest-entry.py \
        --input {TMP_DIR}/entry-001.json \
        --input {TMP_DIR}/entry-002.json \
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
from lib.symbols import extract_python_symbols

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
    calls = entry.get("calls", [])
    if calls:
        section_data["calls"] = calls

    # Preserve sections_written for metadata entries
    if "sections_written" in entry:
        section_data["sections_written"] = entry["sections_written"]

    # Upsert: replaces any existing entry for this (document, section)
    manifest["documents"][doc_name][section_name] = section_data

    return manifest


def check_symbols(entry, project_root):
    """Check that symbols in the entry exist in the referenced file_paths.

    Advisory only -- prints warnings to stderr, never affects exit code.
    Skips if: no symbols, metadata entry, no .py files in file_paths,
    or file doesn't exist.
    """
    if entry.get("section") == "_written_sections":
        return

    symbols = entry.get("symbols", [])
    if not symbols:
        return

    file_paths = entry.get("file_paths", [])
    if not file_paths:
        return

    # Only check .py files -- can't extract symbols from yaml, md, etc.
    py_paths = [fp for fp in file_paths if fp.endswith(".py")]
    if not py_paths:
        return

    # Build union of all symbols from .py files
    all_defined = set()
    for rel_path in py_paths:
        abs_path = os.path.join(project_root, rel_path)
        if not os.path.isfile(abs_path):
            continue
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue
        all_defined.update(extract_python_symbols(source))

    # If no symbols could be extracted (all files missing or empty), skip
    if not all_defined:
        return

    # Check each symbol
    for symbol in symbols:
        if symbol not in all_defined:
            paths_str = ", ".join(py_paths)
            print(
                f"WARNING: symbol '{symbol}' not found in file_paths [{paths_str}]. "
                f"Add the file that defines it.",
                file=sys.stderr,
            )


def main():
    parser = argparse.ArgumentParser(
        description="Validate and upsert manifest entries"
    )
    parser.add_argument(
        "--input", required=True, dest="input_files",
        action="append",
        help="Path to temp file with entry JSON (repeatable)",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to reference manifest JSON file",
    )
    parser.add_argument(
        "--project-root", default=None,
        help="Absolute path to project root for resolving file paths (enables symbol validation)",
    )

    args = parser.parse_args()
    manifest_path = os.path.abspath(args.manifest)
    project_root = os.path.abspath(args.project_root) if args.project_root else None

    # Load existing manifest once
    manifest = load_json(manifest_path, default={})

    added = 0
    rejected = 0

    for input_file in args.input_files:
        input_path = os.path.abspath(input_file)

        # Read input from temp file
        try:
            input_data = load_json(input_path)
        except json.JSONDecodeError as e:
            save_rejected(input_path, f"Invalid JSON: {e}")
            rejected += 1
            continue

        if input_data is None:
            save_rejected(input_path, "Input file not found or empty")
            rejected += 1
            continue

        # Validate
        is_valid, error = validate_entry(input_data)
        if not is_valid:
            save_rejected(input_path, error)
            rejected += 1
            continue

        # Advisory symbol check (warnings only, before upsert)
        if project_root:
            check_symbols(input_data, project_root)

        # Upsert into manifest
        upsert_manifest(manifest, input_data)
        added += 1

    # Single atomic write after all entries processed
    if added > 0:
        save_json(manifest_path, manifest)

    audience = os.path.splitext(os.path.basename(manifest_path))[0]
    print(
        f"Added {added} manifest entries to {audience}",
        file=sys.stderr,
    )

    if rejected > 0:
        print(
            f"Rejected {rejected} invalid entries (see .rejected files)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
