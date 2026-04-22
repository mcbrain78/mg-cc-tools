#!/usr/bin/env python3
"""Count trajectory entries that match the current audience filter.

Used by /mg:auto-doc-auditv2 before spawning the convergence assessment
agent: if no entries match, the agent is skipped entirely (avoids the
false-STOP recommendation that occurs when the user changes audience
filter between audit runs).

Match rule (asymmetric):
  - Current filter empty (unfiltered run) → matches every tagged entry.
  - Current filter non-empty             → matches entries whose
    audience_filter equals the current filter exactly (sorted-list
    equality). Does NOT match unfiltered entries.

Legacy entries written before this field existed are never matched but
their count is reported so callers can surface the situation to users.

Usage:
    python3 count-trajectory-entries.py \
        --trajectory-file FILE \
        [--audience-filter "name1,name2"]

Output (stdout): "<matching> <legacy>\n" (two integers, space-separated).
Exit code: always 0.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json


def parse_audience_filter(raw):
    """Parse a comma-separated audience filter into a sorted unique list.

    Empty / whitespace-only input → empty list (unfiltered run).
    Mirrors aggregate-wave-summaries.py.parse_audience_filter so the two
    callers normalize identically.
    """
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"[,\s]+", raw)]
    return sorted({p for p in parts if p})


def count_entries(trajectory, current_filter):
    """Return (matching_count, legacy_count) for the given trajectory.

    Args:
        trajectory: list of trajectory entries (dicts).
        current_filter: sorted unique list of audience names ([] = unfiltered).

    Returns:
        (matching, legacy) where:
          - matching = entries that satisfy the asymmetric match rule
          - legacy   = entries with no audience_filter field at all
    """
    matching = 0
    legacy = 0
    for entry in trajectory:
        if "audience_filter" not in entry:
            legacy += 1
            continue
        entry_filter = entry["audience_filter"] or []
        if not current_filter:
            matching += 1
        elif entry_filter == current_filter:
            matching += 1
    return matching, legacy


def main():
    parser = argparse.ArgumentParser(
        description="Count trajectory entries matching an audience filter",
    )
    parser.add_argument("--trajectory-file", required=True,
                        help="Path to trajectory.json")
    parser.add_argument("--audience-filter", default="",
                        help="Comma-separated audience names "
                             "(empty = unfiltered run)")

    args = parser.parse_args()

    trajectory = load_json(args.trajectory_file, default=[])
    current_filter = parse_audience_filter(args.audience_filter)
    matching, legacy = count_entries(trajectory, current_filter)
    print(f"{matching} {legacy}")


if __name__ == "__main__":
    main()
