#!/usr/bin/env python3
"""Persist what the implement run is doing, so a dead session leaves a trail.

The category checkpoint SHA used to live only in the orchestrator's conversation
context. That was survivable while the tool reset back to it automatically, and
is not now: the tool no longer undoes anything on a cross-category regression,
it stops and reports the range for a human to decide about. If the session dies
between the failing batch and the report being written, a SHA held only in
context is gone, and the commits it delimits become an unexplained pile on the
user's branch.

So the checkpoint is written to disk when it is taken, and the halt is recorded
before the report is produced. A fresh session can then read this file and say
exactly which category was in flight and which commit range belongs to it.

Written with the same atomic temp-file + os.replace pattern as
update-findings.py, so a kill mid-write cannot leave a torn JSON file that the
next run would choke on.

Usage:
    record-run-state.py set-checkpoint --state <path> --category <name> --checkpoint <sha>
    record-run-state.py mark-halted    --state <path> --reason <text> [--head <sha>]
    record-run-state.py clear          --state <path>
    record-run-state.py read           --state <path>
"""

import argparse
import json
import os
import sys
import tempfile


def _write_atomic(path, data):
    parent = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".run-state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def cmd_set_checkpoint(args):
    state = _read(args.state)
    state.update(
        {
            "status": "in_progress",
            "category": args.category,
            "checkpoint_sha": args.checkpoint,
        }
    )
    state.pop("halt_reason", None)
    state.pop("head_sha", None)
    _write_atomic(args.state, state)
    print(
        f"CHECKPOINT: category '{args.category}' starts at {args.checkpoint} "
        f"(recorded in {args.state})"
    )
    return 0


def cmd_mark_halted(args):
    state = _read(args.state)
    if not state.get("checkpoint_sha"):
        print(
            "WARNING: no checkpoint recorded; the halt record will not identify a "
            "commit range",
            file=sys.stderr,
        )
    state["status"] = "halted"
    state["halt_reason"] = args.reason
    if args.head:
        state["head_sha"] = args.head
    _write_atomic(args.state, state)
    rng = (
        f"{state.get('checkpoint_sha')}..{args.head}"
        if state.get("checkpoint_sha") and args.head
        else "(range unknown)"
    )
    print(f"HALTED: recorded in {args.state}; batch range {rng}")
    return 0


def cmd_clear(args):
    if os.path.exists(args.state):
        os.remove(args.state)
        print(f"CLEARED: removed {args.state}")
    else:
        print(f"CLEARED: {args.state} was not present")
    return 0


def cmd_read(args):
    state = _read(args.state)
    if not state:
        print("NO-STATE: no run state recorded")
        return 0
    print(json.dumps(state, indent=2))
    return 1 if state.get("status") == "halted" else 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Persist implement-run checkpoint and halt state."
    )
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("set-checkpoint", help="record a category's starting commit")
    sc.add_argument("--state", required=True)
    sc.add_argument("--category", required=True)
    sc.add_argument("--checkpoint", required=True)
    sc.set_defaults(func=cmd_set_checkpoint)

    mh = sub.add_parser("mark-halted", help="record that the run stopped")
    mh.add_argument("--state", required=True)
    mh.add_argument("--reason", required=True)
    mh.add_argument("--head", help="HEAD sha at the moment of the halt")
    mh.set_defaults(func=cmd_mark_halted)

    cl = sub.add_parser("clear", help="remove the state file")
    cl.add_argument("--state", required=True)
    cl.set_defaults(func=cmd_clear)

    rd = sub.add_parser("read", help="print state; exit 1 if halted")
    rd.add_argument("--state", required=True)
    rd.set_defaults(func=cmd_read)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
