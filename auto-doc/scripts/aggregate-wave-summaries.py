#!/usr/bin/env python3
"""Aggregate multiple per-document wave summaries into a single summary.

After the audit runs wave-summary.py once per document, this script merges
the per-document summaries into one aggregate summary for the trajectory.

Usage:
    python3 aggregate-wave-summaries.py \
        --summaries FILE [FILE ...] \
        --output FILE

Output: merged JSON with combined counts across all documents.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def aggregate(summaries):
    """Merge multiple wave summary dicts into one.

    Args:
        summaries: list of wave summary dicts (from wave-summary.py).

    Returns:
        Single merged summary dict.
    """
    if not summaries:
        return {
            "wave": 0,
            "findings": {"new": 0, "by_check": {}, "by_suggestion_category": {}},
            "dismissals": {"total": 0, "by_tier": {}},
            "uncleared_remaining": 0,
            "entities_resolved_this_wave": 0,
        }

    merged_by_check = {}
    merged_by_suggestion = {}
    merged_by_tier = {}
    total_new = 0
    total_dismissed = 0
    total_uncleared = 0
    total_resolved = 0

    # Use the wave number from the first summary (they should all match)
    wave = summaries[0].get("wave", 0)

    for s in summaries:
        findings = s.get("findings", {})
        total_new += findings.get("new", 0)
        for k, v in findings.get("by_check", {}).items():
            merged_by_check[k] = merged_by_check.get(k, 0) + v
        for k, v in findings.get("by_suggestion_category", {}).items():
            merged_by_suggestion[k] = merged_by_suggestion.get(k, 0) + v

        dismissals = s.get("dismissals", {})
        total_dismissed += dismissals.get("total", 0)
        for k, v in dismissals.get("by_tier", {}).items():
            merged_by_tier[k] = merged_by_tier.get(k, 0) + v

        total_uncleared += s.get("uncleared_remaining", 0)
        total_resolved += s.get("entities_resolved_this_wave", 0)

    return {
        "wave": wave,
        "findings": {
            "new": total_new,
            "by_check": merged_by_check,
            "by_suggestion_category": merged_by_suggestion,
        },
        "dismissals": {
            "total": total_dismissed,
            "by_tier": merged_by_tier,
        },
        "uncleared_remaining": total_uncleared,
        "entities_resolved_this_wave": total_resolved,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate per-document wave summaries into one",
    )
    parser.add_argument("--summaries", nargs="+", required=True,
                        help="Paths to per-document wave summary JSONs")
    parser.add_argument("--output", required=True,
                        help="Output path for merged summary JSON")

    args = parser.parse_args()

    summaries = []
    for path in args.summaries:
        s = load_json(path, default=None)
        if s is not None:
            summaries.append(s)

    merged = aggregate(summaries)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    save_json(args.output, merged)
    print(
        f"Aggregated {len(summaries)} summaries: "
        f"{merged['findings']['new']} new findings, "
        f"{merged['dismissals']['total']} dismissals, "
        f"{merged['uncleared_remaining']} uncleared remaining",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
