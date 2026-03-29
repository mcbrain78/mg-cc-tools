#!/usr/bin/env python3
"""Archive verify run outputs alongside a context transcript.

Creates a named directory under .mg/docs/verify-runs/ containing the
verify findings, report, and the user's context transcript. The folder
name is derived from the context file's basename (without extension).

Usage:
    python3 archive-verify.py \
        --context-file /tmp/rr1-602-verify3.txt \
        [--project-root /path/to/project]

The script copies:
    - .mg/docs/docs-verify-findings.json
    - .mg/docs/docs-verify-report.md
    - The context file itself

Into: .mg/docs/verify-runs/{context-basename}/
"""

import argparse
import os
import shutil
import sys


def find_project_root(start_dir):
    """Walk up from start_dir looking for .mg/docs/.

    Args:
        start_dir: Directory to start searching from.

    Returns:
        Project root path, or None if not found.
    """
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, ".mg", "docs")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def main():
    parser = argparse.ArgumentParser(
        description="Archive verify outputs with context transcript"
    )
    parser.add_argument(
        "--context-file", required=True,
        help="Path to the context transcript file",
    )
    parser.add_argument(
        "--project-root", default=None,
        help="Project root (default: auto-detect from cwd)",
    )

    args = parser.parse_args()

    context_file = os.path.abspath(args.context_file)
    if not os.path.isfile(context_file):
        print(f"Error: context file not found: {context_file}", file=sys.stderr)
        sys.exit(1)

    # Determine project root
    if args.project_root:
        project_root = os.path.abspath(args.project_root)
    else:
        project_root = find_project_root(os.getcwd())
        if project_root is None:
            print(
                "Error: could not find .mg/docs/ in current or parent directories. "
                "Use --project-root to specify.",
                file=sys.stderr,
            )
            sys.exit(1)

    mg_docs = os.path.join(project_root, ".mg", "docs")

    # Check source files exist
    findings_src = os.path.join(mg_docs, "docs-verify-findings.json")
    report_src = os.path.join(mg_docs, "docs-verify-report.md")

    missing = []
    if not os.path.isfile(findings_src):
        missing.append(findings_src)
    if not os.path.isfile(report_src):
        missing.append(report_src)

    if missing:
        print(
            f"Error: missing verify outputs: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Derive folder name from context file basename
    folder_name = os.path.splitext(os.path.basename(context_file))[0]
    run_dir = os.path.join(mg_docs, "verify-runs", folder_name)

    if os.path.exists(run_dir):
        print(f"Error: archive already exists: {run_dir}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(run_dir)

    # Copy files
    shutil.copy2(findings_src, os.path.join(run_dir, "docs-verify-findings.json"))
    shutil.copy2(report_src, os.path.join(run_dir, "docs-verify-report.md"))
    shutil.copy2(context_file, os.path.join(run_dir, os.path.basename(context_file)))

    print(f"Archived to {run_dir}:")
    print(f"  docs-verify-findings.json")
    print(f"  docs-verify-report.md")
    print(f"  {os.path.basename(context_file)}")


if __name__ == "__main__":
    main()
