#!/usr/bin/env python3
"""Register a hook script in a Claude Code settings.json, idempotently.

Every tool that ships a hook used to hand-roll this merge in embedded Python
inside its post-install.md, and each one drifted from the others:

  * Two of them wrote a plain relative command path in --project mode, which
    breaks the moment the session cd's out of the project root.
  * cc-regression-test wrote a relative path at install time and an absolute
    one from its runtime command, so its "already registered?" test — exact
    string equality — never matched, and every sync run appended another
    duplicate entry.
  * transcript tested for the absolute hook path as a substring, which a
    project-mode command never contains, so it too appended a duplicate on
    every re-run while reporting "ADDED" as a fresh registration.
  * One reported a rewrite whenever it stripped and re-added entries, even
    when the resulting file was byte-identical — inventing a restart the user
    did not need.

So the merge is canonicalising rather than append-if-absent: strip every entry
that references our hook, then append exactly one entry per matcher. That is
idempotent by construction, and it repairs the duplicates the old code left
behind instead of adding to them.

The result is decided by comparing the serialised output against the original
bytes, so UNCHANGED means the file genuinely did not move. Callers key their
restart advice off that: hook *registration* is snapshotted by Claude Code at
session start, whereas the hook script itself is a subprocess spawned per
event, so new script content is live on the next tool call.
"""

import argparse
import json
import os
import shutil
import sys

VALID_MODES = ("project", "global", "target")


def build_command(install_mode, hook_rel_path, hook_abs_path):
    """Return the command string to store in settings.json.

    In project mode the command is rooted at $CLAUDE_PROJECT_DIR, which Claude
    Code exports for hook commands regardless of the session's working
    directory. That survives both a mid-session `cd` and a clone of the repo
    into a different filesystem layout (cloud workers), which a relative path
    does not and a baked absolute path does not respectively.
    """
    if install_mode == "project":
        if not hook_rel_path:
            raise ValueError("--hook-rel-path is required in project mode")
        rel = hook_rel_path.lstrip("/")
        return f'python3 "$CLAUDE_PROJECT_DIR/{rel}"'
    if not hook_abs_path:
        raise ValueError(f"--hook-abs-path is required in {install_mode} mode")
    return f"python3 {hook_abs_path}"


def canonicalise(settings, event, matchers, marker, command):
    """Strip every entry referencing `marker`, then append one per matcher.

    Returns the number of stripped hook commands. Entries belonging to other
    tools are preserved, including sibling hooks inside an entry we partly
    own — only the hooks whose command mentions our marker are removed, and an
    entry is dropped only once it has no hooks left.

    Stripping is deliberately not filtered by matcher: an entry referencing our
    hook is ours wherever it ended up, and matching on matcher is what let
    cc-regression-test accumulate duplicates under mismatched matchers.
    """
    hooks = settings.setdefault("hooks", {})
    existing = hooks.setdefault(event, [])

    stripped = 0
    kept = []
    for entry in existing:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        entry_hooks = entry.get("hooks", [])
        if not isinstance(entry_hooks, list):
            kept.append(entry)
            continue
        surviving = [
            hk
            for hk in entry_hooks
            if not (isinstance(hk, dict) and marker in hk.get("command", ""))
        ]
        stripped += len(entry_hooks) - len(surviving)
        if surviving:
            kept.append({**entry, "hooks": surviving})
        elif not entry_hooks:
            # An entry that never had hooks is not ours to drop.
            kept.append(entry)

    for matcher in matchers:
        kept.append(
            {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}
        )

    hooks[event] = kept
    return stripped


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Idempotently register a hook script in a Claude Code settings.json."
    )
    p.add_argument("--settings", required=True, help="path to settings.json")
    p.add_argument("--install-mode", required=True, choices=VALID_MODES)
    p.add_argument(
        "--hook-rel-path",
        help="hook path relative to the project root, e.g. "
        ".claude/transcript/hooks/inject-transcript-path.py (project mode)",
    )
    p.add_argument(
        "--hook-abs-path", help="absolute hook path (global/target mode)"
    )
    p.add_argument(
        "--marker",
        help="substring identifying this tool's entries; defaults to the hook "
        "filename, which is what makes the match mode-independent",
    )
    p.add_argument(
        "--matcher",
        action="append",
        required=True,
        dest="matchers",
        help="tool matcher to register (repeatable)",
    )
    p.add_argument("--event", default="PreToolUse", help="hook event name")
    p.add_argument("--indent", type=int, default=2)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report the result without writing",
    )
    args = p.parse_args(argv)

    try:
        command = build_command(
            args.install_mode, args.hook_rel_path, args.hook_abs_path
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    marker = args.marker or os.path.basename(
        args.hook_rel_path or args.hook_abs_path or ""
    )
    if not marker:
        print(
            "ERROR: --marker could not be derived; pass it explicitly",
            file=sys.stderr,
        )
        return 2

    before = None
    try:
        with open(args.settings) as f:
            before = f.read()
        settings = json.loads(before)
    except FileNotFoundError:
        settings = {}
    except json.JSONDecodeError:
        # Keep the unreadable file rather than silently discarding whatever the
        # user had in it; starting from {} without a copy loses real config.
        backup = args.settings + ".bak"
        shutil.copy2(args.settings, backup)
        print(f"WARNING: {args.settings} is not valid JSON; backed up to {backup}")
        before = None
        settings = {}

    if not isinstance(settings, dict):
        print(
            f"ERROR: {args.settings} does not contain a JSON object", file=sys.stderr
        )
        return 2

    stripped = canonicalise(
        settings, args.event, args.matchers, marker, command
    )
    after = json.dumps(settings, indent=args.indent) + "\n"

    n = len(args.matchers)
    if after == before:
        print(
            f"UNCHANGED: {n} canonical {args.event} entr{'y' if n == 1 else 'ies'} "
            f"for {marker} already present in {args.settings}"
        )
        return 0

    if not args.dry_run:
        with open(args.settings, "w") as f:
            f.write(after)

    if stripped:
        print(
            f"REWROTE: removed {stripped} stale {marker} entr"
            f"{'y' if stripped == 1 else 'ies'}; wrote {n} canonical "
            f"{args.event} entr{'y' if n == 1 else 'ies'} to {args.settings}"
        )
    else:
        print(
            f"ADDED: wrote {n} {args.event} entr{'y' if n == 1 else 'ies'} "
            f"for {marker} to {args.settings}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
