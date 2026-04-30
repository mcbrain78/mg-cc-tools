#!/usr/bin/env python3
"""Append a wave summary to the cumulative trajectory log.

Usage:
    python3 append-trajectory.py \
        --trajectory-file FILE \
        --wave-summary FILE

Loads the trajectory (JSON array), appends the wave summary, saves.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def append_trajectory(trajectory_file, wave_summary_file):
    """Append wave summary to trajectory log.

    Returns:
        The updated trajectory list.
    """
    trajectory = load_json(trajectory_file, default=[])
    summary = load_json(wave_summary_file, default={})

    if not summary:
        print("Warning: empty wave summary, skipping", file=sys.stderr)
        return trajectory

    trajectory.append(summary)

    os.makedirs(os.path.dirname(os.path.abspath(trajectory_file)), exist_ok=True)
    save_json(trajectory_file, trajectory)
    print(
        f"Trajectory: {len(trajectory)} waves recorded",
        file=sys.stderr,
    )
    return trajectory


def main():
    parser = argparse.ArgumentParser(
        description="Append wave summary to cumulative trajectory log",
    )
    parser.add_argument("--trajectory-file", required=True,
                        help="Path to trajectory.json")
    parser.add_argument("--wave-summary", required=True,
                        help="Path to the wave summary JSON to append")

    args = parser.parse_args()
    append_trajectory(
        trajectory_file=args.trajectory_file,
        wave_summary_file=args.wave_summary,
    )


if __name__ == "__main__":
    main()
