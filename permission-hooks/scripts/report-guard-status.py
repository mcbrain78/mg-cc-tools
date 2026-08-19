#!/usr/bin/env python3
"""Report the rule inventory of an installed permission-guard.py.

Run at the end of the permission-hooks post-install to show what actually landed
in the target: how many rules per category, and whether PROJECT_ROOT is a baked
absolute path or the placeholder that resolves at runtime.

Loading is by file path rather than by module name. `permission-guard` is not a
legal identifier, so the inline version this replaces had to reach it through
`sys.path.insert` plus `importlib.import_module` with a hyphenated string -- which
also meant that if the target directory happened to contain another module the
guard imports, the wrong one could win. A file-path loader names exactly one file
and pollutes nothing.

Importing runs the guard's module body. That is the point: a file that cannot be
imported is a file the hook runtime cannot use either, so a failure here is a real
install failure and is reported as one rather than swallowed.

Usage:
    report-guard-status.py --hook <path to installed permission-guard.py>
"""

import argparse
import importlib.util
import os
import sys

WIDTH = 50


def load_guard(hook_path):
    spec = importlib.util.spec_from_file_location("mg_permission_guard", hook_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {hook_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report(guard, out=sys.stdout):
    categories = getattr(guard, "CATEGORIES", None)
    if not isinstance(categories, dict):
        raise AttributeError(
            "the hook does not expose a CATEGORIES dict -- either it is not a "
            "permission-guard, or the copy is truncated"
        )

    print("Permission Guard -- Rule Categories:", file=out)
    print("=" * WIDTH, file=out)
    total = 0
    for category, patterns in categories.items():
        count = len(patterns)
        total += count
        print(f"  {category}: {count} rules", file=out)
    print("=" * WIDTH, file=out)
    print(f"  Total: {total} rules + out-of-project path guard", file=out)
    print(file=out)

    project_root = getattr(guard, "PROJECT_ROOT", None)
    print(f"  PROJECT_ROOT: {project_root!r}", file=out)
    if not project_root or str(project_root).startswith("{"):
        print(
            "  (unresolved placeholder -- resolves at runtime via "
            "CLAUDE_PROJECT_DIR, then event cwd)",
            file=out,
        )
    return total


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Report rule categories of an installed permission-guard.py."
    )
    p.add_argument(
        "--hook",
        required=True,
        help="path to the INSTALLED permission-guard.py in the target project",
    )
    args = p.parse_args(argv)

    if not os.path.isfile(args.hook):
        print(f"ERROR: no such file: {args.hook}", file=sys.stderr)
        return 1

    try:
        guard = load_guard(args.hook)
    except BaseException as exc:
        print(
            f"ERROR: could not import {args.hook}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        report(guard)
    except AttributeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
