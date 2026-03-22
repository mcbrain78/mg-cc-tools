#!/usr/bin/env python3
"""Merge per-audience scan JSON files into a single docs-scan.json.

Called by the scan orchestrator after all audience scanner subagents
complete. Reads per-audience JSON files from scan-dir, merges their
contents with deduplication, and writes a single docs-scan.json
conforming to the schema in references/schema.md.

Usage:
    python3 merge-scan.py \
        --scan-dir <project>/.mg/docs/scan-logs \
        --output <project>/.mg/docs/docs-scan.json \
        --project-name "my-project" \
        --root-path "/absolute/path/to/project" \
        [--mode initial]

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

# Severity ordering for staleness deduplication (higher index = higher severity)
SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def severity_rank(severity):
    """Return numeric rank for severity string (higher = more severe)."""
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return -1


def merge_source_material(existing, new_entries):
    """Merge source_material_index entries.

    For duplicate keys, keep the entry with more source_files.
    """
    for key, entry in new_entries.items():
        if key not in existing:
            existing[key] = entry
        else:
            # Keep the one with more source files
            existing_count = len(existing[key].get("source_files", []))
            new_count = len(entry.get("source_files", []))
            if new_count > existing_count:
                existing[key] = entry
    return existing


def merge_staleness(existing, new_entries):
    """Merge staleness_report entries.

    Deduplicate by (document, section), keeping highest severity.
    """
    # Index existing by (document, section)
    by_key = {}
    for entry in existing:
        key = (entry.get("document", ""), entry.get("section", ""))
        if key not in by_key or severity_rank(entry.get("severity", "")) > severity_rank(by_key[key].get("severity", "")):
            by_key[key] = entry

    for entry in new_entries:
        key = (entry.get("document", ""), entry.get("section", ""))
        if key not in by_key or severity_rank(entry.get("severity", "")) > severity_rank(by_key[key].get("severity", "")):
            by_key[key] = entry

    return list(by_key.values())


def merge_gap_analysis(existing, new_gap):
    """Merge gap_analysis data.

    undocumented_components: union of both lists.
    missing_for_audience: union per audience.
    """
    # Merge undocumented_components (union, no duplicates)
    existing_undoc = set(existing.get("undocumented_components", []))
    new_undoc = set(new_gap.get("undocumented_components", []))
    existing["undocumented_components"] = sorted(existing_undoc | new_undoc)

    # Merge missing_for_audience per audience (union)
    existing_missing = existing.get("missing_for_audience", {})
    new_missing = new_gap.get("missing_for_audience", {})
    for audience, items in new_missing.items():
        if audience not in existing_missing:
            existing_missing[audience] = list(items)
        else:
            merged = set(existing_missing[audience]) | set(items)
            existing_missing[audience] = sorted(merged)
    existing["missing_for_audience"] = existing_missing

    return existing


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-audience scan JSON files into docs-scan.json"
    )
    parser.add_argument(
        "--scan-dir", required=True,
        help="Directory containing per-audience scan JSON files"
    )
    parser.add_argument(
        "--output", required=True,
        help="Path for merged docs-scan.json output"
    )
    parser.add_argument(
        "--project-name", required=True,
        help="Project name"
    )
    parser.add_argument(
        "--root-path", required=True,
        help="Project root path"
    )
    parser.add_argument(
        "--mode", default="initial",
        choices=["initial", "update"],
        help="Scan mode (default: initial)"
    )

    args = parser.parse_args()

    scan_dir = os.path.abspath(args.scan_dir)
    if not os.path.isdir(scan_dir):
        print(f"Error: scan directory not found: {scan_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect all .json files in scan directory
    pattern = os.path.join(scan_dir, "*.json")
    json_files = sorted(glob.glob(pattern))

    # Merged state
    source_material = {}
    staleness_report = []
    note_classifications = []
    gap_analysis = {
        "undocumented_components": [],
        "missing_for_audience": {},
    }
    project_model = None
    gsd_context = None

    files_processed = 0
    for json_file in json_files:
        try:
            data = load_json(json_file)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: skipping {os.path.basename(json_file)}: {e}",
                  file=sys.stderr)
            continue

        if data is None:
            print(f"Warning: skipping {os.path.basename(json_file)}: empty file",
                  file=sys.stderr)
            continue

        if not isinstance(data, dict):
            print(f"Warning: skipping {os.path.basename(json_file)}: not a JSON object",
                  file=sys.stderr)
            continue

        files_processed += 1

        # Merge source_material_index
        if "source_material_index" in data:
            source_material = merge_source_material(
                source_material, data["source_material_index"]
            )

        # Merge staleness_report
        if "staleness_report" in data:
            staleness_report = merge_staleness(
                staleness_report, data["staleness_report"]
            )

        # Concatenate note_classifications
        if "note_classifications" in data:
            note_classifications.extend(data["note_classifications"])

        # Merge gap_analysis
        if "gap_analysis" in data:
            gap_analysis = merge_gap_analysis(gap_analysis, data["gap_analysis"])

        # Take project_model from first file that has it
        if project_model is None and "project_model" in data:
            project_model = data["project_model"]

        # Take gsd_context from first file that has it
        if gsd_context is None and "gsd_context" in data:
            gsd_context = data["gsd_context"]

    # Build output with all required top-level fields
    output_data = {
        "project": args.project_name,
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "root_path": args.root_path,
        "mode": args.mode,
        "project_model": project_model,
        "source_material_index": source_material,
        "staleness_report": staleness_report,
        "note_classifications": note_classifications,
        "gap_analysis": gap_analysis,
        "gsd_context": gsd_context,
    }

    # Save atomically
    output_path = os.path.abspath(args.output)
    save_json(output_path, output_data)

    staleness_count = len(staleness_report)
    material_count = len(source_material)
    print(
        f"Merged {files_processed} scan files into {args.output}. "
        f"{material_count} source material entries, "
        f"{staleness_count} staleness issues.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
