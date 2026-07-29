#!/usr/bin/env python3
"""Publish Claude Code's usage limits so the permission guard can gate on them.

    python3 usage-watch.py [--session-max 93] [--weekly-max 98] [--interval 600]
    python3 usage-watch.py --once            # one read, for testing

A plain OS process — no Claude session, no agent, no tokens. Every tick it reads
the real limits via usage-read.py (~1.7s, free) and writes one account-wide file,
`<session-base>/usage.json`. That is the whole job: nothing per-session, no state
to keep, no session directories touched.

The guard pulls rather than the daemon pushing, and that is the important part.
Every guarded tool call reads the published verdict, so a session that starts
working one minute after a tick is gated immediately instead of waiting up to a
full interval for someone to notice it — and no latch is ever written into a
session directory that might outlive its session.

The daemon owns the policy: it compares against the thresholds and publishes
`over` / `binding` / `pct` / `window_iso`, leaving the hook a file read and two
comparisons. Change the thresholds in the systemd unit; nothing needs
reinstalling.

Thresholds are late by design — the risk being managed is walking into a
rate-limit error mid-task, not reserving budget. They also stay above
/mg:spec-improve-auto's own 75%/90% round-boundary gate, which pauses cleanly and
schedules its own resume: its gate check and CronCreate are tool calls a gate
would block, so that loop must always shut itself down first.

A session silences the warning for the current window with
`auto-approve-session.py mute-session-limit <id>`; the guard reads that, the
daemon neither knows nor cares.

Stdlib-only: runs under systemd with plain python3, no venv.
"""
import argparse
import fcntl
import importlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_ur = importlib.import_module("usage-read")
_aas = importlib.import_module("auto-approve-session")

DEFAULT_SESSION_MAX = 93
DEFAULT_WEEKLY_MAX = 98
# 10 minutes. Detection lag no longer depends on this — the guard reads the
# published file on every call — so the tick only bounds how quickly a *crossing*
# becomes visible, which the thresholds' headroom absorbs.
DEFAULT_INTERVAL_S = 600
LOCK_FILENAME = "mg-usage-watch.lock"


def _log(msg):
    print(f"{datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def published_path():
    return Path(_aas._session_base()) / _aas.USAGE_FILENAME


# ── verdict ──────────────────────────────────────────────────────────────────

def verdict(reading, session_max, weekly_max, now_ms=None):
    """Turn a reading into the record the guard consumes.

    Weekly binds ahead of session: a session reset does not clear a weekly cap,
    so when both are over, the weekly window is the one that matters.
    """
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    record = dict(reading)
    record["read_at_ms"] = now_ms
    record["session_max"] = session_max
    record["weekly_max"] = weekly_max
    record.update({"over": False, "binding": None, "pct": None,
                   "window_iso": None, "window_human": None})
    if not reading.get("ok"):
        return record
    for kind, limit in (("weekly", weekly_max), ("session", session_max)):
        pct = reading.get(f"{kind}_pct")
        if pct is not None and pct > limit:
            record.update({
                "over": True, "binding": kind, "pct": pct,
                "window_iso": reading.get(f"{kind}_reset_iso"),
                "window_human": reading.get(f"{kind}_reset"),
            })
            break
    return record


def publish(record):
    """Write the reading atomically — the guard reads this on every tool call."""
    path = published_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(record, f)
    os.replace(tmp, path)


# ── tick ─────────────────────────────────────────────────────────────────────

def run_once(session_max, weekly_max, timeout):
    reading = _ur.read_usage(timeout)
    record = verdict(reading, session_max, weekly_max)
    publish(record)
    if not reading.get("ok"):
        # Published anyway, with ok:false — the guard treats that as "no gate",
        # so a monitoring failure never blocks work.
        _log(f"usage unreadable ({reading.get('error')}) — published, no gate")
        return record
    state = (f"GATE ON ({record['binding']} {record['pct']}%, "
             f"resets {record['window_human']})" if record["over"] else "clear")
    _log(f"session {reading['session_pct']}% / weekly {reading['weekly_pct']}% "
         f"(limits {session_max}/{weekly_max}) — {state}")
    return record


def acquire_lock():
    """One publisher per machine. Returns the held file object, or None."""
    path = Path(_aas._session_base()) / LOCK_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-max", type=int, default=DEFAULT_SESSION_MAX)
    parser.add_argument("--weekly-max", type=int, default=DEFAULT_WEEKLY_MAX)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_S,
                        help="seconds between reads (default: 600)")
    parser.add_argument("--timeout", type=int, default=_ur.DEFAULT_TIMEOUT_S)
    parser.add_argument("--once", action="store_true", help="one read, then exit")
    parser.add_argument("--no-lock", action="store_true",
                        help="skip the single-instance lock (for a manual --once)")
    args = parser.parse_args(argv)

    lock = None
    if not args.no_lock:
        lock = acquire_lock()
        if lock is None:
            _log("another usage-watch holds the lock — exiting")
            return 2
    try:
        if args.once:
            run_once(args.session_max, args.weekly_max, args.timeout)
            return 0
        _log(f"publishing usage every {args.interval}s; guard gates above "
             f"session {args.session_max}% / weekly {args.weekly_max}%")
        while True:
            try:
                run_once(args.session_max, args.weekly_max, args.timeout)
            except Exception as e:                  # a tick must never kill the watch
                _log(f"tick failed: {e!r}")
            time.sleep(args.interval)
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
