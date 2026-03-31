#!/usr/bin/env python3
"""Audit pass control — decides whether the prose auditor should continue.

Tracks per-section pass counts. Each call increments the counter for the
given section and returns whether to continue auditing that section.

Usage:
    audit-pass-control.py --state-file PATH --section SLUG

Returns JSON to stdout:
    {"continue": true, "pass": 2, "section": "monitoring-alerting"}
    {"continue": false, "pass": 3, "section": "monitoring-alerting"}
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

MAX_PASSES = 3


def main():
    parser = argparse.ArgumentParser(
        description="Audit pass control for prose verification",
    )
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--section", required=True)

    args = parser.parse_args()

    state = load_json(args.state_file)
    if state is None:
        state = {}

    section_pass = state.get(args.section, 0) + 1
    state[args.section] = section_pass
    save_json(args.state_file, state)

    should_continue = section_pass < MAX_PASSES

    print(json.dumps({
        "continue": should_continue,
        "pass": section_pass,
        "section": args.section,
    }))


if __name__ == "__main__":
    main()
