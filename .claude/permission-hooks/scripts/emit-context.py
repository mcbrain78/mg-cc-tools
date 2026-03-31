#!/usr/bin/env python3
"""Emit a session context marker for permission-guard auto-approval.

Usage:
    python3 emit-context.py <COMMAND_NAME>

Prints a SESSION_CONTEXT_ID line that the permission-guard hook recognises.
The human must approve execution of this script (stage-0 gate), making the
printed marker the trust anchor for subsequent auto-approvals.
"""
import sys
import time


def main():
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("Usage: emit-context.py <COMMAND_NAME>", file=sys.stderr)
        sys.exit(1)

    command_name = sys.argv[1].upper()
    timestamp_ms = int(time.time() * 1000)
    print(f"SESSION_CONTEXT_ID: MG:{command_name}_{timestamp_ms}")


if __name__ == "__main__":
    main()
