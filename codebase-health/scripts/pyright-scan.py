#!/usr/bin/env python3
"""Pyright diagnostics filtered by target category for codebase-health pipeline.

Runs pyright once and splits results into two buckets:
- dead_code_paths: reportUnreachable, reportUnusedExpression, reportUnusedVariable
- contract_drift: reportReturnType, reportArgumentType, reportCallIssue,
                  reportIndexIssue, reportGeneralTypeIssues

Usage:
    python3 pyright-scan.py --root <path> --output <path> [--ignore-file <path>]

Requires: npm install -g pyright (or npx pyright)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ignore import load_ignore_patterns, should_ignore

DEAD_CODE_RULES = {
    "reportUnreachable",
    "reportUnusedExpression",
    "reportUnusedVariable",
}

CONTRACT_DRIFT_RULES = {
    "reportReturnType",
    "reportArgumentType",
    "reportCallIssue",
    "reportIndexIssue",
    "reportGeneralTypeIssues",
}


def find_pyright():
    """Find pyright executable. Returns command list or exits with error."""
    if shutil.which("pyright"):
        return ["pyright"]
    if shutil.which("npx"):
        result = subprocess.run(
            ["npx", "--yes", "pyright", "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return ["npx", "--yes", "pyright"]
    print(
        "Error: pyright is not installed.\n"
        "Install it with: npm install -g pyright (or npx pyright)",
        file=sys.stderr,
    )
    sys.exit(1)


def scan(root, ignore_file=None):
    """Run pyright scan and categorize diagnostics.

    Returns structured JSON-serializable dict.
    """
    pyright_cmd = find_pyright()
    patterns = load_ignore_patterns(ignore_file)

    cmd = pyright_cmd + ["--outputjson"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=root,
    )

    # pyright returns non-zero when diagnostics are found, which is expected
    # Parse stdout as JSON regardless of exit code
    stdout = result.stdout.strip()
    if not stdout:
        # No output — pyright may have failed to run
        if result.stderr:
            print(f"pyright stderr: {result.stderr}", file=sys.stderr)
        return {
            "summary": {"total": 0, "dead_code_paths": 0, "contract_drift": 0},
            "dead_code_paths": [],
            "contract_drift": [],
        }

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"Error parsing pyright JSON output: {e}", file=sys.stderr)
        print(f"First 500 chars of stdout: {stdout[:500]}", file=sys.stderr)
        sys.exit(1)

    dead_code_paths = []
    contract_drift = []

    diagnostics = raw.get("generalDiagnostics", [])
    for diag in diagnostics:
        filepath = diag.get("file", "")
        if not filepath:
            continue

        # Make path relative to root
        if os.path.isabs(filepath):
            rel_path = os.path.relpath(filepath, root)
        else:
            rel_path = filepath

        # Skip ignored files
        abs_path = os.path.join(root, rel_path) if not os.path.isabs(filepath) else filepath
        if should_ignore(abs_path, patterns, root):
            continue

        rule = diag.get("rule", "")
        severity = diag.get("severity", "information")
        message = diag.get("message", "")

        range_info = diag.get("range", {})
        start = range_info.get("start", {})
        end = range_info.get("end", {})
        line_start = start.get("line", 0)
        line_end = end.get("line", line_start)

        entry = {
            "file": rel_path,
            "line_start": line_start,
            "line_end": line_end,
            "rule": rule,
            "severity": severity,
            "message": message,
        }

        if rule in DEAD_CODE_RULES:
            dead_code_paths.append(entry)
        elif rule in CONTRACT_DRIFT_RULES:
            contract_drift.append(entry)

    return {
        "summary": {
            "total": len(dead_code_paths) + len(contract_drift),
            "dead_code_paths": len(dead_code_paths),
            "contract_drift": len(contract_drift),
        },
        "dead_code_paths": dead_code_paths,
        "contract_drift": contract_drift,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pyright diagnostics filtered by target category"
    )
    parser.add_argument("--root", required=True, help="Project root directory")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument(
        "--ignore-file", default=None, help="Path to .health-ignore file"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Auto-detect .health-ignore if not specified
    if args.ignore_file is None:
        default_ignore = os.path.join(root, ".mg", "health-scan", ".health-ignore")
        if os.path.isfile(default_ignore):
            args.ignore_file = default_ignore

    result = scan(root, args.ignore_file)

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Print summary to stderr
    summary = result["summary"]
    print(
        f"Found {summary['total']} relevant diagnostics: "
        f"{summary['dead_code_paths']} dead-code-paths, "
        f"{summary['contract_drift']} contract-drift",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
