#!/usr/bin/env python3
"""Split docs-scan.json into per-audience or glossary view files.

Reads a full docs-scan.json and produces a filtered view file containing
only the data relevant to a specific audience or the glossary writer.
Each view file has 3 top-level keys (gsd_context, source_material_index,
gap_analysis). project_model is extracted to a separate standalone file
via --project-model-output to avoid duplicating it across all views.

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
        --documents ARCHITECTURE,DEVELOPER_GUIDE \\
        --project-model-output /tmp/project-model.json

    python3 split-scan-by-audience.py \\
        --input .mg/docs/docs-scan.json \\
        --output /tmp/scan-view-glossary.json \\
        --mode glossary

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


# Keys to include in every view file (project_model extracted separately)
VIEW_KEYS = ("gsd_context", "source_material_index", "gap_analysis")


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


def slim_project_model(pm):
    """Deep-copy project_model and strip bulky fields from components.

    Removes ``public_api`` from each component entry -- writers get
    this data from source files via Serena, so duplicating it in the
    extracted model wastes tokens. Preserves ``database_tables`` for
    section-to-table mapping in db-table-map.json.

    Args:
        pm: The project_model dict from docs-scan.json.

    Returns:
        New dict with slimmed components.
    """
    slimmed = copy.deepcopy(pm)
    for comp in slimmed.get("components", []):
        comp.pop("public_api", None)
    # Strip LLM-generated schema detail (now extracted deterministically
    # into database-model.json). Keep lightweight metadata like engine,
    # orm_framework, and migration_tool.
    db = slimmed.get("database")
    if isinstance(db, dict):
        db.pop("schemas", None)
        db.pop("design_notes", None)
    return slimmed


def build_view(data, source_material_index, gap_analysis):
    """Assemble a view file with the 3 standard top-level keys.

    project_model is extracted separately via --project-model-output
    to avoid duplicating it across all view files.

    Args:
        data: Full docs-scan.json data.
        source_material_index: Pre-filtered source material index.
        gap_analysis: Pre-filtered gap analysis.

    Returns:
        Dict with exactly 3 top-level keys.
    """
    return {
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
    parser.add_argument(
        "--project-model-output", dest="project_model_output",
        help="Path to write slimmed project-model.json (skipped if file already exists)",
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

    # Write slimmed project_model to standalone file (once, first caller wins)
    if args.project_model_output:
        pm_path = os.path.abspath(args.project_model_output)
        if not os.path.exists(pm_path):
            pm = slim_project_model(data.get("project_model", {}))
            save_json(pm_path, pm)
            print("Wrote project-model.json", file=sys.stderr)

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
