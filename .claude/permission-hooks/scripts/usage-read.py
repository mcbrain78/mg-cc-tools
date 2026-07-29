#!/usr/bin/env python3
"""Read Claude Code's real subscription limits, cost-free.

    python3 usage-read.py [--timeout 60]

Prints one JSON object:

    {"ok": true,
     "session_pct": 93, "session_reset": "Jul 29, 6:49pm",
     "session_reset_iso": "2026-07-29T18:49:00",
     "weekly_pct": 28,  "weekly_reset": "Aug 3, 8:59pm",
     "weekly_reset_iso": "2026-08-03T20:59:00",
     "error": null}

``ok: false`` means the numbers could not be read — CLI missing, timeout,
network failure, unparseable output. Callers must treat that as *unknown*, never
as a breach: stopping a run because monitoring hiccuped is worse than the limit
itself, which merely cuts off and resets. See usage-watch.py.

The read costs nothing: `/usage` reports ``num_turns: 0``, ``total_cost_usd: 0``
and zero token usage, because it is not a model turn.

``--no-session-persistence`` is required rather than cosmetic. Without it every
read persists a throwaway session transcript under ~/.claude/projects whose only
user entry is ``/usage`` — which then appears as a phantom row at the top of the
/mg:auto-approve-session picker — and pays ~3s of extra startup (1.7s vs 4.7s
measured).

Only the two "Current …" lines are authoritative. The "What's contributing to
your limits usage" block below them is explicitly approximate and local-machine
only, so it is ignored.

Parsing mirrors spec/scripts/spec_checks.py. That is a different tool family, so
the logic is duplicated rather than imported (see CLAUDE.md) — keep the two in
sync. Stdlib-only: this runs under systemd with plain python3, no venv.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

USAGE_CMD = ["claude", "-p", "/usage", "--output-format", "json",
             "--no-session-persistence"]
DEFAULT_TIMEOUT_S = 60

_PCT_RE = re.compile(r"(\d+)%\s*used")
_RESET_RE = re.compile(r"resets\s+(.+?)\s*(?:\(|$)")
_SESSION_PREFIX = "Current session:"
_WEEKLY_PREFIX = "Current week (all models):"


def _parse_usage_line(line):
    """'Current session: 93% used · resets Jul 29, 6:49pm (…)' → (93, 'Jul 29, 6:49pm')."""
    pm = _PCT_RE.search(line)
    rm = _RESET_RE.search(line)
    return (int(pm.group(1)) if pm else None,
            rm.group(1).strip() if rm else None)


def parse_reset(s, now=None):
    """'Jul 29, 6:49pm' → a future naive-local datetime.

    `/usage` prints local time, so no timezone maths. A reset always lies ahead,
    which is how a year boundary is resolved (a 'Jan 2' read in December).

    On the hour the minutes are omitted — 'Aug 3, 9pm' — so the minuteless formats
    are not optional: without them such a window parses to None, and a gate bound
    to it could never be matched by a mute.
    """
    if not s:
        return None
    s2 = re.sub(r"(?i)\b(am|pm)\b", lambda m: m.group(1).upper(), s.strip().rstrip("."))
    now = datetime.now() if now is None else now
    parsed = None
    for fmt in ("%b %d, %I:%M%p", "%b %d %I:%M%p", "%B %d, %I:%M%p",
                "%b %d, %I%p", "%b %d %I%p", "%B %d, %I%p"):
        try:
            parsed = datetime.strptime(s2, fmt).replace(year=now.year)
            break
        except ValueError:
            parsed = None
    if parsed is None:
        return None
    while parsed < now - timedelta(hours=1):   # fix a year underflow
        parsed = parsed.replace(year=parsed.year + 1)
    return parsed


def parse_usage(body, now=None):
    """Extract both limits from `/usage` output text.

    Returns the reading dict. ``ok`` is False when either line is missing, since
    a partial reading is not something a threshold should be compared against.
    """
    reading = {
        "ok": False, "error": None,
        "session_pct": None, "session_reset": None, "session_reset_iso": None,
        "weekly_pct": None, "weekly_reset": None, "weekly_reset_iso": None,
    }
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(_SESSION_PREFIX):
            reading["session_pct"], reading["session_reset"] = _parse_usage_line(stripped)
        elif stripped.startswith(_WEEKLY_PREFIX):
            reading["weekly_pct"], reading["weekly_reset"] = _parse_usage_line(stripped)

    if reading["session_pct"] is None or reading["weekly_pct"] is None:
        reading["error"] = "could not parse session/weekly lines from /usage output"
        return reading

    for key in ("session", "weekly"):
        dt = parse_reset(reading[f"{key}_reset"], now)
        reading[f"{key}_reset_iso"] = dt.isoformat() if dt else None
    reading["ok"] = True
    return reading


def read_usage(timeout=DEFAULT_TIMEOUT_S, now=None):
    """Run the CLI and return a reading dict. Never raises."""
    try:
        proc = subprocess.run(USAGE_CMD, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"could not run /usage: {e}",
                "session_pct": None, "session_reset": None, "session_reset_iso": None,
                "weekly_pct": None, "weekly_reset": None, "weekly_reset_iso": None}
    if proc.returncode != 0:
        return {"ok": False, "error": f"/usage exited {proc.returncode}",
                "session_pct": None, "session_reset": None, "session_reset_iso": None,
                "weekly_pct": None, "weekly_reset": None, "weekly_reset_iso": None}
    try:
        envelope = json.loads(proc.stdout)
        body = "" if envelope.get("is_error") else envelope.get("result", "")
    except (json.JSONDecodeError, AttributeError):
        body = proc.stdout          # tolerate a plain-text CLI
    return parse_usage(body, now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help="seconds to wait for the CLI (default: 60)")
    args = parser.parse_args(argv)
    reading = read_usage(args.timeout)
    print(json.dumps(reading))
    return 0 if reading["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
