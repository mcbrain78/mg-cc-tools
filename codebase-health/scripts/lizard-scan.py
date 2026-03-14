#!/usr/bin/env python3
"""Complexity and size analysis via lizard for codebase-health pipeline.

Runs lizard as a subprocess to measure per-function NLOC, cyclomatic
complexity, parameter count, and (with -ENS) nesting depth.  Normalizes
output into the pipeline's JSON format with threshold-based filtering.

Usage:
    python3 lizard-scan.py --root <path> --output <path> [--ignore-file <path>]

Requires: pip install lizard
"""

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ignore import load_ignore_patterns, should_ignore

# ── Thresholds ──────────────────────────────────────────────────────────────
# Functions below ALL thresholds are dropped from output.
# The agent applies severity classification on top of these.

THRESHOLD_NLOC = 60          # lines of code per function
THRESHOLD_CCN = 15           # cyclomatic complexity
THRESHOLD_PARAMS = 5         # parameter count
THRESHOLD_NESTING = 4        # max nesting depth (requires -ENS)
THRESHOLD_FILE_LINES = 500   # total lines per file


def find_lizard():
    """Find lizard executable. Returns command list or exits with error."""
    if shutil.which("lizard"):
        return ["lizard"]
    # Try as a Python module
    result = subprocess.run(
        [sys.executable, "-m", "lizard", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        return [sys.executable, "-m", "lizard"]
    print(
        "Error: lizard is not installed.\n"
        "Install it with: pip install lizard",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_csv_output(csv_text, root, patterns):
    """Parse lizard CSV output into structured function records.

    Returns list of dicts with per-function metrics.
    """
    functions = []
    reader = csv.DictReader(io.StringIO(csv_text))

    for row in reader:
        filepath = row.get("file", row.get("File", ""))
        if not filepath:
            continue

        # Make path absolute then relative to root
        if not os.path.isabs(filepath):
            filepath = os.path.join(root, filepath)
        abs_path = os.path.abspath(filepath)

        if should_ignore(abs_path, patterns, root):
            continue

        rel_path = os.path.relpath(abs_path, root)

        try:
            nloc = int(row.get("NLOC", row.get("nloc", 0)))
            ccn = int(row.get("CCN", row.get("ccn", 0)))
            tokens = int(row.get("Token", row.get("token", 0)))
            params = int(row.get("Param", row.get("param",
                         row.get("PARAM", row.get("parameter_count", 0)))))
            length = int(row.get("Length", row.get("length", 0)))
            start_line = int(row.get("Start line", row.get("start_line", 0)))
            end_line = int(row.get("End line", row.get("end_line", 0)))
            # -ENS extension adds a "Max nesting" or "Nesting" column
            nesting = int(row.get("Max nesting",
                          row.get("Max Nesting",
                          row.get("Nesting", row.get("nesting", 0)))))
        except (ValueError, TypeError):
            continue

        func_name = row.get("Name", row.get("name",
                    row.get("Function", row.get("function", "?"))))

        # Apply threshold filter: keep if ANY metric exceeds its threshold
        if (nloc < THRESHOLD_NLOC
                and ccn < THRESHOLD_CCN
                and params < THRESHOLD_PARAMS
                and nesting < THRESHOLD_NESTING):
            continue

        functions.append({
            "file": rel_path,
            "function": func_name,
            "start_line": start_line,
            "end_line": end_line,
            "nloc": nloc,
            "ccn": ccn,
            "tokens": tokens,
            "params": params,
            "length": length,
            "nesting": nesting,
        })

    return functions


def count_file_lines(root, patterns):
    """Count total lines per source file, return those exceeding threshold.

    Returns list of dicts with file-level size info.
    """
    bloated_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not should_ignore(os.path.join(dirpath, d), patterns, root)
        ]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if should_ignore(fpath, patterns, root):
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = sum(1 for _ in f)
            except (OSError, UnicodeDecodeError):
                continue

            if lines >= THRESHOLD_FILE_LINES:
                bloated_files.append({
                    "file": os.path.relpath(fpath, root),
                    "lines": lines,
                })

    bloated_files.sort(key=lambda x: x["lines"], reverse=True)
    return bloated_files


def scan(root, ignore_file=None):
    """Run lizard + file size analysis on the project root.

    Returns structured JSON-serializable dict.
    """
    lizard_cmd = find_lizard()
    patterns = load_ignore_patterns(ignore_file)

    # Build lizard command with CSV output and nesting depth extension
    cmd = lizard_cmd + [
        root,
        "--csv",
        "-ENS",           # nesting depth extension
        "-C", "0",        # dump all functions (no CCN threshold)
        "-L", "0",        # dump all functions (no NLOC threshold)
        "-a", "0",        # dump all functions (no param threshold)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=root,
    )

    # lizard returns 0 even when functions exceed thresholds (unless -W is used)
    if result.returncode != 0 and not result.stdout:
        print(f"lizard error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    functions = parse_csv_output(result.stdout, root, patterns)
    bloated_files = count_file_lines(root, patterns)

    # Sort functions by composite "sprawl score" (ccn * nloc) descending
    functions.sort(key=lambda f: f["ccn"] * f["nloc"], reverse=True)

    return {
        "summary": {
            "functions_flagged": len(functions),
            "files_flagged": len(bloated_files),
            "thresholds": {
                "nloc": THRESHOLD_NLOC,
                "ccn": THRESHOLD_CCN,
                "params": THRESHOLD_PARAMS,
                "nesting": THRESHOLD_NESTING,
                "file_lines": THRESHOLD_FILE_LINES,
            },
        },
        "functions": functions,
        "bloated_files": bloated_files,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Complexity and size analysis via lizard"
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

    summary = result["summary"]
    print(
        f"Found {summary['functions_flagged']} functions exceeding thresholds, "
        f"{summary['files_flagged']} bloated files",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
