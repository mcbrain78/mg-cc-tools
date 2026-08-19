#!/usr/bin/env python3
"""Write the per-document session config that audit-cmd.py reads.

The session file is ten paths plus three scalars, and every one of the paths is a
pure function of the workspace, audience and document. The inline version this
replaces made the orchestrator interpolate all ten by hand, once per document per
wave -- a transcription surface with no upside, where a single mistyped path
produces a session that resolves to a file nobody writes and an agent that
silently finds nothing to do.

So the script takes the four values the paths are derived FROM and derives them,
which makes a wrong path a bug here (once, testable) rather than a typo there
(every wave, invisible).

Key names and layout are fixed by audit-cmd.py, which indexes this file directly;
`workspace` is written because the format has always carried it, though nothing
currently reads it.

Usage:
    write-session-config.py --workspace <dir> --audience <name>
                            --document <NAME> --wave <N> [--output <path>]
"""

import argparse
import json
import os
import sys


def session_paths(workspace, audience, document):
    """The ten paths, all derived. run/ holds per-run state, the level above it
    holds state that outlives a run (not-entities, protected, covered, suppressed)."""
    auditv2 = os.path.join(workspace, "auditv2")
    run = os.path.join(auditv2, "run")
    stem = f"{audience}-{document}"
    prose_verify_dir = os.path.join(run, f"prose-verify-{stem}")
    return {
        "prose_verify_dir": prose_verify_dir,
        "uncleared_file": os.path.join(run, f"uncleared-{stem}.json"),
        "findings_file": os.path.join(run, f"findings-prose-{stem}.json"),
        "sections_filter": os.path.join(prose_verify_dir, "affected-sections.json"),
        "not_entities_file": os.path.join(auditv2, "not-entities.json"),
        "dismissed_this_run_file": os.path.join(run, "dismissed-this-run.json"),
        "protected_entities_file": os.path.join(auditv2, "protected-entities.json"),
        "suppress_file": os.path.join(auditv2, "suppressed-findings.json"),
        "covered_entities_file": os.path.join(auditv2, "covered-entities.json"),
    }


def build_session(workspace, audience, document, wave):
    session = {
        "workspace": workspace,
        "document": document,
        "audience": audience,
        "wave": wave,
    }
    session.update(session_paths(workspace, audience, document))
    return session


def default_output(workspace, audience, document):
    return os.path.join(
        workspace, "auditv2", "run", f"session-{audience}-{document}.json"
    )


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Write a per-document auditv2 resolution session config."
    )
    p.add_argument("--workspace", required=True, help="the auto-doc workspace dir")
    p.add_argument("--audience", required=True)
    p.add_argument("--document", required=True)
    p.add_argument("--wave", required=True, type=int, help="current wave number")
    p.add_argument(
        "--output",
        help="where to write; defaults to <workspace>/auditv2/run/session-<audience>-<document>.json",
    )
    args = p.parse_args(argv)

    if args.wave < 1:
        print(f"ERROR: --wave must be 1 or greater, got {args.wave}", file=sys.stderr)
        return 2

    session = build_session(
        args.workspace, args.audience, args.document, args.wave
    )
    output = args.output or default_output(
        args.workspace, args.audience, args.document
    )

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w") as f:
        json.dump(session, f, indent=2)
        f.write("\n")

    print(f"SESSION: wave {args.wave} for {args.audience}/{args.document} -> {output}")

    missing = [
        f"{key} -> {session[key]}"
        for key in ("uncleared_file", "prose_verify_dir", "sections_filter")
        if not os.path.exists(session[key])
    ]
    if missing:
        # Not fatal: the caller may be staging the session before the inputs are
        # in place. But a wave spawned against a missing uncleared file finds no
        # work and reports success, so say so rather than let it pass silently.
        print("WARNING: session references paths that do not exist yet:", file=sys.stderr)
        for entry in missing:
            print(f"  {entry}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
