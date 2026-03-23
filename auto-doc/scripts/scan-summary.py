"""Extract summary counts from docs-scan.json.

Prints key=value lines to stdout for the orchestrator to parse.
Keeps the full scan JSON out of the orchestrator's context.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json


def main():
    parser = argparse.ArgumentParser(
        description="Extract summary counts from docs-scan.json"
    )
    parser.add_argument(
        "--scan-file", required=True, help="Path to docs-scan.json"
    )
    args = parser.parse_args()

    scan_path = os.path.abspath(args.scan_file)
    d = load_json(scan_path)
    if d is None:
        print("Error: scan file not found", file=sys.stderr)
        sys.exit(1)

    smi = len(d.get("source_material_index", {}))
    stale = len(d.get("staleness_report", []))
    notes = len(d.get("note_classifications", []))
    gap = d.get("gap_analysis", {})
    undoc = len(gap.get("undocumented_components", []))
    missing = {k: len(v) for k, v in gap.get("missing_for_audience", {}).items()}
    pm = d.get("project_model", {})
    tech = len(pm.get("tech_stack", []))
    comps = len(pm.get("components", []))
    eps = len(pm.get("entry_points", []))
    gsd = d.get("gsd_context")

    print(f"mode={d.get('mode')}")
    print(f"tech_stack={tech}")
    print(f"components={comps}")
    print(f"entry_points={eps}")
    print(f"source_material={smi}")
    print(f"staleness={stale}")
    print(f"notes={notes}")
    print(f"undocumented={undoc}")
    print(f"missing={json.dumps(missing)}")
    print(f"gsd_milestone={gsd.get('milestone') if gsd else 'none'}")
    print(f"gsd_phases={len(gsd.get('completed_phases', [])) if gsd else 0}")


if __name__ == "__main__":
    main()
