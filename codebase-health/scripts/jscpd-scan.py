#!/usr/bin/env python3
"""Token-level copy-paste detection via jscpd for codebase-health pipeline.

Runs jscpd as a subprocess to detect duplicated code blocks, then normalizes
the output into the pipeline's JSON format.

Usage:
    python3 jscpd-scan.py --root <path> --output <path> [--ignore-file <path>]

Requires: npm install -g jscpd (or npx jscpd)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ignore import load_ignore_patterns, should_ignore


def find_jscpd():
    """Find jscpd executable. Returns command list or exits with error."""
    if shutil.which("jscpd"):
        return ["jscpd"]
    # Try npx
    if shutil.which("npx"):
        result = subprocess.run(
            ["npx", "--yes", "jscpd", "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return ["npx", "--yes", "jscpd"]
    print(
        "Error: jscpd is not installed.\n"
        "Install it with: npm install -g jscpd",
        file=sys.stderr,
    )
    sys.exit(1)


def convert_ignore_patterns(patterns):
    """Convert .health-ignore patterns to jscpd --ignore glob format."""
    globs = []
    for p in patterns:
        clean = p.rstrip("/")
        if "*" in clean:
            globs.append(f"**/{clean}")
        else:
            globs.append(f"**/{clean}/**")
    return globs


def scan(root, ignore_file=None):
    """Run jscpd scan on the project root.

    Returns structured JSON-serializable dict.
    """
    jscpd_cmd = find_jscpd()
    patterns = load_ignore_patterns(ignore_file)

    tmpdir = tempfile.mkdtemp(prefix="jscpd-")
    try:
        cmd = jscpd_cmd + [
            root,
            "--reporters", "json",
            "--min-lines", "6",
            "--min-tokens", "50",
            "--mode", "mild",
            "--gitignore",
            "--output", tmpdir,
        ]

        # Add ignore patterns
        ignore_globs = convert_ignore_patterns(patterns)
        for glob in ignore_globs:
            cmd.extend(["--ignore", glob])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=root,
        )

        # jscpd returns non-zero when duplicates are found, which is expected
        # Only fail on actual errors (missing binary, etc.)
        if result.returncode != 0 and not result.stdout and "Error" in result.stderr:
            print(f"jscpd error: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Read the jscpd JSON report
        report_path = os.path.join(tmpdir, "jscpd-report.json")
        if not os.path.isfile(report_path):
            # No duplicates found — return empty result
            return {
                "summary": {
                    "total_clones": 0,
                    "total_duplicated_lines": 0,
                    "percentage": 0.0,
                },
                "clones": [],
            }

        with open(report_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # Normalize jscpd output
    clones = []
    total_dup_lines = 0

    for dup in raw.get("duplicates", []):
        first = dup.get("firstFile", {})
        second = dup.get("secondFile", {})

        file_a = os.path.relpath(
            os.path.join(root, first.get("name", "")), root
        )
        file_b = os.path.relpath(
            os.path.join(root, second.get("name", "")), root
        )

        # Skip if either file is ignored
        if should_ignore(os.path.join(root, file_a), patterns, root):
            continue
        if should_ignore(os.path.join(root, file_b), patterns, root):
            continue

        start_a = first.get("startLoc", {}).get("line", 0)
        end_a = first.get("endLoc", {}).get("line", 0)
        start_b = second.get("startLoc", {}).get("line", 0)
        end_b = second.get("endLoc", {}).get("line", 0)

        lines = max(end_a - start_a, end_b - start_b, 0)
        total_dup_lines += lines

        clones.append({
            "file_a": file_a,
            "lines_a": [start_a, end_a],
            "file_b": file_b,
            "lines_b": [start_b, end_b],
            "tokens": dup.get("tokens", 0),
            "lines": lines,
        })

    # Compute percentage from raw statistics if available
    stats = raw.get("statistics", {})
    percentage = stats.get("total", {}).get("percentage", 0.0)

    return {
        "summary": {
            "total_clones": len(clones),
            "total_duplicated_lines": total_dup_lines,
            "percentage": round(percentage, 2),
        },
        "clones": clones,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Token-level copy-paste detection via jscpd"
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
        f"Found {summary['total_clones']} clone pairs, "
        f"{summary['total_duplicated_lines']} duplicated lines "
        f"({summary['percentage']}%)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
