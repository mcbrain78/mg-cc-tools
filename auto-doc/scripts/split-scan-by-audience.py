#!/usr/bin/env python3
"""Split docs-scan.json into per-audience or glossary view files.

Reads a full docs-scan.json and produces a filtered view file containing
only the data relevant to a specific audience or the glossary writer.
Each view file has the same 4 top-level keys (project_model, gsd_context,
source_material_index, gap_analysis) so writer agents' access patterns
work unchanged.

source_files arrays are stripped from all view files -- writers fetch
per-section source files on demand via get-section-sources.py.

Audience mode:
    Filters source_material_index to only keys whose document prefix
    (text before first "/") matches the --documents list. Filters
    gap_analysis.missing_for_audience to only the target audience.

Glossary mode:
    Preserves all source_material_index keys (no document filtering).
    Includes full gap_analysis (all audiences).

Usage:
    python3 split-scan-by-audience.py \\
        --input .mg/docs/docs-scan.json \\
        --output /tmp/scan-view-developers.json \\
        --mode audience \\
        --audience developers \\
        --documents ARCHITECTURE,DEVELOPER_GUIDE

    python3 split-scan-by-audience.py \\
        --input .mg/docs/docs-scan.json \\
        --output /tmp/scan-view-glossary.json \\
        --mode glossary

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


# Keys to include in every view file
VIEW_KEYS = ("project_model", "gsd_context", "source_material_index", "gap_analysis")


def filter_source_material(index, document_list):
    """Filter source_material_index to entries matching document_list.

    Keys are in DOCUMENT/section-slug format. Keeps entries where the
    document prefix (text before first "/") is in document_list.

    Args:
        index: The source_material_index dict from docs-scan.json.
        document_list: List of uppercase document names to keep.

    Returns:
        Filtered dict with only matching entries.
    """
    result = {}
    doc_set = set(document_list)
    for key, value in index.items():
        doc_prefix = key.split("/", 1)[0]
        if doc_prefix in doc_set:
            result[key] = value
    return result


def filter_gap_analysis(gap, audience):
    """Filter gap_analysis to a single audience.

    Preserves undocumented_components verbatim. Filters
    missing_for_audience to only the target audience key.

    Args:
        gap: The gap_analysis dict from docs-scan.json.
        audience: Audience key to keep (e.g., "developers").

    Returns:
        Filtered gap_analysis dict.
    """
    result = {
        "undocumented_components": gap.get("undocumented_components", []),
        "missing_for_audience": {},
    }
    mfa = gap.get("missing_for_audience", {})
    if audience in mfa:
        result["missing_for_audience"][audience] = mfa[audience]
    return result


def strip_source_files(index):
    """Remove source_files from each entry in the index.

    Writers fetch source_files on demand via get-section-sources.py,
    so view files only need section keys, staleness, and synthesized_from.

    Args:
        index: The source_material_index dict.

    Returns:
        New dict with source_files removed from each entry.
    """
    result = {}
    for key, value in index.items():
        entry = {k: v for k, v in value.items() if k != "source_files"}
        result[key] = entry
    return result


def build_view(data, source_material_index, gap_analysis):
    """Assemble a view file with the 4 standard top-level keys.

    Args:
        data: Full docs-scan.json data.
        source_material_index: Pre-filtered source material index.
        gap_analysis: Pre-filtered gap analysis.

    Returns:
        Dict with exactly 4 top-level keys.
    """
    return {
        "project_model": data.get("project_model", {}),
        "gsd_context": data.get("gsd_context", None),
        "source_material_index": source_material_index,
        "gap_analysis": gap_analysis,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Split docs-scan.json into per-audience or glossary view files"
    )
    parser.add_argument(
        "--input", required=True, dest="input_file",
        help="Path to docs-scan.json",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the view file",
    )
    parser.add_argument(
        "--mode", required=True, choices=["audience", "glossary"],
        help="Filtering mode: audience or glossary",
    )
    parser.add_argument(
        "--audience",
        help="Audience key (required for audience mode)",
    )
    parser.add_argument(
        "--documents",
        help="Comma-separated uppercase document names (required for audience mode)",
    )

    args = parser.parse_args()

    # Validate audience mode requirements
    if args.mode == "audience":
        if not args.audience:
            print("Error: --audience is required in audience mode", file=sys.stderr)
            sys.exit(1)
        if not args.documents:
            print("Error: --documents is required in audience mode", file=sys.stderr)
            sys.exit(1)

    # Load input
    data = load_json(os.path.abspath(args.input_file), default={})

    raw_index = data.get("source_material_index", {})
    raw_gap = data.get("gap_analysis")

    if args.mode == "audience":
        document_list = [d.strip() for d in args.documents.split(",")]
        filtered_index = strip_source_files(
            filter_source_material(raw_index, document_list)
        )
        filtered_gap = filter_gap_analysis(raw_gap, args.audience) if raw_gap else {}
    else:
        # Glossary mode
        filtered_index = strip_source_files(raw_index)
        filtered_gap = raw_gap if raw_gap is not None else {}

    view = build_view(data, filtered_index, filtered_gap)
    save_json(os.path.abspath(args.output), view)

    entry_count = len(filtered_index)
    mode_label = f"{args.mode}"
    if args.mode == "audience":
        mode_label = f"audience:{args.audience}"
    print(
        f"Wrote {mode_label} view: {entry_count} source material entries",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
