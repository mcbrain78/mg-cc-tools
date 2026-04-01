#!/usr/bin/env python3
"""Emit an edit guard marker to toggle Edit/Write permission gating.

Usage:
    python3 emit-edit-guard.py <ON|OFF>

Prints a SESSION_FEATURE line that the permission-guard hook recognises.
ON  = edits allowed (default state)
OFF = edits blocked until re-enabled
"""
import sys
import time


def main():
    if len(sys.argv) != 2 or sys.argv[1].upper() not in ("ON", "OFF"):
        print("Usage: emit-edit-guard.py <ON|OFF>", file=sys.stderr)
        sys.exit(1)

    state = sys.argv[1].upper()
    ts = int(time.time() * 1000)
    print(f"SESSION_FEATURE: MG:EDIT_GUARD_{state}_{ts}")


if __name__ == "__main__":
    main()
