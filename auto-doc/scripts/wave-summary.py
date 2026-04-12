#!/usr/bin/env python3
"""Produce a structured per-wave summary of audit findings and dismissals.

Usage:
    python3 wave-summary.py \
        --findings-file FILE \
        --prev-findings-file FILE \
        --uncleared-file FILE \
        --dismissed-file FILE \
        --wave N \
        --output FILE

Output: JSON with finding counts by check and suggestion category,
dismissal counts by tier, and uncleared remaining count.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


# Keyword patterns for classifying suggestion text into broad categories.
# Checked in order; first match wins.
_SUGGESTION_PATTERNS = [
    ("missing_code_ref", re.compile(
        r"function|method|class|module|import|code|script", re.I)),
    ("missing_db_ref", re.compile(
        r"table|column|schema|database|db\b", re.I)),
    ("missing_env_ref", re.compile(
        r"env|environment variable", re.I)),
    ("missing_config_ref", re.compile(
        r"config|\.yaml|\.toml|\.ini|\.json|settings", re.I)),
    ("missing_dep_ref", re.compile(
        r"dependency|package|library|dep\b", re.I)),
    ("cosmetic", re.compile(
        r"formatting|cosmetic|style|wording|rephrase|rename", re.I)),
]


def _classify_suggestion(suggestion):
    """Classify a suggestion string into a broad category."""
    if not suggestion:
        return "unclear"
    for category, pattern in _SUGGESTION_PATTERNS:
        if pattern.search(suggestion):
            return category
    return "unclear"


# Known dismissal tier keywords found in reason text from dismiss-entity.py.
_TIER_PATTERNS = [
    ("ref_covers_it", re.compile(r"ref covers|already covered|declared ref", re.I)),
    ("universal", re.compile(r"universal|builtin|keyword|generic|formatting", re.I)),
    ("no_ref_type", re.compile(r"no.*ref type|cannot.*ref|no constructible|external url|third.party|framework state", re.I)),
    ("contextual", re.compile(r"contextual|plain prose|plain english", re.I)),
]


def _classify_dismissal_tier(entry):
    """Classify a dismissed entity into a tier based on available info."""
    reason = entry.get("reason", "")
    for tier, pattern in _TIER_PATTERNS:
        if pattern.search(reason):
            return tier
    return "other"


def wave_summary(findings_file, prev_findings_file, uncleared_file,
                 dismissed_file, wave):
    """Build a structured summary for the given wave.

    Returns:
        dict with wave summary data.
    """
    findings = load_json(findings_file, default=[])
    prev_findings = load_json(prev_findings_file, default=[])
    uncleared = load_json(uncleared_file, default=[])
    dismissed = load_json(dismissed_file, default=[])

    # New findings = those in current but not in previous
    prev_set = {
        (f.get("section", ""), f.get("check", ""), f.get("description", ""))
        for f in prev_findings
    }
    new_findings = [
        f for f in findings
        if (f.get("section", ""), f.get("check", ""), f.get("description", ""))
        not in prev_set
    ]

    # Count by check type
    by_check = {}
    for f in new_findings:
        check = f.get("check", "unknown")
        by_check[check] = by_check.get(check, 0) + 1

    # Count by suggestion category
    by_suggestion = {}
    for f in new_findings:
        cat = _classify_suggestion(f.get("suggestion", ""))
        by_suggestion[cat] = by_suggestion.get(cat, 0) + 1

    # Dismissal counts by tier
    by_tier = {}
    for d in dismissed:
        tier = _classify_dismissal_tier(d)
        by_tier[tier] = by_tier.get(tier, 0) + 1

    return {
        "wave": wave,
        "findings": {
            "new": len(new_findings),
            "by_check": by_check,
            "by_suggestion_category": by_suggestion,
        },
        "dismissals": {
            "total": len(dismissed),
            "by_tier": by_tier,
        },
        "uncleared_remaining": len(uncleared),
        "entities_resolved_this_wave": len(new_findings) + len(dismissed),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Produce a structured per-wave audit summary",
    )
    parser.add_argument("--findings-file", required=True,
                        help="Current findings file")
    parser.add_argument("--prev-findings-file", required=True,
                        help="Previous wave's findings file (for diff)")
    parser.add_argument("--uncleared-file", required=True,
                        help="Current uncleared entities file")
    parser.add_argument("--dismissed-file", required=True,
                        help="Dismissed entities for this run")
    parser.add_argument("--wave", type=int, required=True,
                        help="Wave number")
    parser.add_argument("--output", required=True,
                        help="Output path for wave summary JSON")

    args = parser.parse_args()

    summary = wave_summary(
        findings_file=args.findings_file,
        prev_findings_file=args.prev_findings_file,
        uncleared_file=args.uncleared_file,
        dismissed_file=args.dismissed_file,
        wave=args.wave,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    save_json(args.output, summary)
    print(
        f"Wave {args.wave}: {summary['findings']['new']} new findings, "
        f"{summary['dismissals']['total']} dismissals, "
        f"{summary['uncleared_remaining']} uncleared remaining",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
