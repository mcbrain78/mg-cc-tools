#!/usr/bin/env python3
"""Validate and atomically write scan agent output.

Called by scan agents after producing complete output for one audience.
The agent writes scan data to a temp file (via Write tool), then
invokes this script with --input pointing to that file. The script
validates required fields and key format, rejects invalid input to
a .rejected file, and writes the validated output atomically.

Usage:
    python3 write-scan-output.py \
        --input .mg/docs/scan/scan-developers.json \
        --output .mg/docs/scan/scan-developers.json \
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

# Valid project_model fields for synthesized_from validation
VALID_SYNTH_FIELDS = {
    "tech_stack", "entry_points", "components",
    "infrastructure", "database", "user_interfaces",
}


def _load_sections_files(paths):
    """Load parsed template JSONs and build per-document lookup.

    Returns dict: {DOCUMENT: {"valid_slugs": set, "sections": {slug: section_dict}}}
    """
    templates = {}
    for path in paths:
        data = load_json(path)
        if data is None:
            print(f"Warning: sections file not found: {path}", file=sys.stderr)
            continue
        doc = data.get("document", "")
        slug_set = set(data.get("valid_slugs", []))
        sections_by_slug = {}
        for s in data.get("sections", []):
            sections_by_slug[s["slug"]] = s
        templates[doc] = {"valid_slugs": slug_set, "sections": sections_by_slug}
    return templates


def validate_content(data, templates):
    """Validate SMI entries against parsed template sections.

    Returns (errors, warnings) where errors cause rejection and
    warnings are logged but don't block.
    """
    errors = []
    warnings = []
    smi = data.get("source_material_index", {})

    # Track which template sections have entries
    seen_sections = {}  # doc -> set of slugs

    for key, entry in smi.items():
        parts = key.split("/", 1)
        if len(parts) != 2:
            continue
        doc_name, slug = parts

        if doc_name not in templates:
            continue

        tmpl = templates[doc_name]

        if doc_name not in seen_sections:
            seen_sections[doc_name] = set()
        seen_sections[doc_name].add(slug)

        # Slug membership check
        if slug not in tmpl["valid_slugs"]:
            errors.append(
                f"Invalid slug '{slug}' for {doc_name}: "
                f"not in template sections"
            )
            continue

        section = tmpl["sections"].get(slug, {})

        # No invented synthesized_from
        entry_synth = entry.get("synthesized_from")
        tmpl_synth = section.get("synthesized_from")
        if entry_synth and not tmpl_synth:
            errors.append(
                f"{key}: entry has synthesized_from but template "
                f"section does not"
            )

        # Valid synthesized_from paths
        if entry_synth:
            for path in entry_synth:
                parts = path.split(".")
                if (
                    len(parts) != 2
                    or parts[0] != "project_model"
                    or parts[1] not in VALID_SYNTH_FIELDS
                ):
                    errors.append(
                        f"{key}: invalid synthesized_from path '{path}'"
                    )

    # Completeness check: non-optional sections missing from SMI
    for doc_name, tmpl in templates.items():
        doc_seen = seen_sections.get(doc_name, set())
        for slug, section in tmpl["sections"].items():
            if slug not in doc_seen and not section.get("optional", False):
                warnings.append(
                    f"{doc_name}/{slug}: non-optional template section "
                    f"missing from scan output"
                )

    return errors, warnings


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
    parser.add_argument(
        "--sections-file", action="append", default=[],
        help="Parsed template JSON for content validation (repeatable)",
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

    # Structural validation
    is_valid, errors = validate_scan_output(input_data)
    if not is_valid:
        reason = "; ".join(errors)
        save_rejected(input_path, reason)
        sys.exit(1)

    # Content validation against parsed templates (if provided)
    if args.sections_file:
        templates = _load_sections_files(
            [os.path.abspath(p) for p in args.sections_file]
        )
        if templates:
            content_errors, content_warnings = validate_content(
                input_data, templates
            )
            for w in content_warnings:
                print(f"Warning: {w}", file=sys.stderr)
            if content_errors:
                reason = "; ".join(content_errors)
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
