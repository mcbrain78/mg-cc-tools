#!/usr/bin/env python3
"""Move a completed run directory into history under the next free number.

Both auditv2 and fix archive their previous run the same way, and both used to
do it with an inline `python3 -c` block inside a bash `if`. The two copies had
already drifted apart in one respect -- fix's copy looked for its history in
`auditv2/history` while naming entries `fix-N` -- which is preserved here
deliberately: the two run types share one history directory and are told apart by
their prefix, so a caller passes `--history-dir` and `--prefix` explicitly rather
than having either inferred.

Numbering is max-plus-one over existing `<prefix>-<N>` entries, not a count, so a
gap left by a manually deleted archive cannot cause a collision that would
clobber history.

The sentinel is what distinguishes "a previous run finished" from "a previous run
was interrupted or never happened". Only a directory containing it is archived;
anything else is left alone for the caller to overwrite, because a half-finished
run is not worth a history slot.

Usage:
    archive-run.py --run-dir <dir> --history-dir <dir> --prefix <name>
                   --sentinel <filename>
"""

import argparse
import os
import re
import sys


def next_number(history_dir, prefix):
    """One past the highest existing <prefix>-<N>, or 1 if there are none."""
    if not os.path.isdir(history_dir):
        return 1
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    numbers = [
        int(m.group(1))
        for name in os.listdir(history_dir)
        if (m := pattern.match(name))
    ]
    return max(numbers) + 1 if numbers else 1


def archive(run_dir, history_dir, prefix, sentinel):
    if not os.path.isdir(run_dir):
        return None, f"SKIPPED: {run_dir} does not exist -- nothing to archive"
    if not os.path.isfile(os.path.join(run_dir, sentinel)):
        return None, (
            f"SKIPPED: {run_dir} has no {sentinel} -- previous run did not "
            f"complete, not archiving it"
        )

    os.makedirs(history_dir, exist_ok=True)
    dest = os.path.join(history_dir, f"{prefix}-{next_number(history_dir, prefix)}")
    if os.path.exists(dest):
        # next_number said this slot was free, so something else took it between
        # the scan and now. Refuse rather than merge into an existing archive.
        return None, f"ERROR: {dest} already exists -- refusing to overwrite history"
    os.rename(run_dir, dest)
    return dest, f"ARCHIVED: {run_dir} -> {dest}"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Archive a completed run directory into numbered history."
    )
    p.add_argument("--run-dir", required=True, help="the run directory to move")
    p.add_argument("--history-dir", required=True, help="where numbered archives live")
    p.add_argument("--prefix", required=True, help="archive name prefix, e.g. audit")
    p.add_argument(
        "--sentinel",
        required=True,
        help="file inside --run-dir that marks the run as completed",
    )
    args = p.parse_args(argv)

    _, message = archive(args.run_dir, args.history_dir, args.prefix, args.sentinel)
    print(message)
    if message.startswith("ERROR:"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
