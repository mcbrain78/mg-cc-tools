#!/usr/bin/env python3
"""Wrap claude -p Haiku verification for section references.

Invokes the section-verifier prompt via claude CLI, parses the structured
JSON response, logs results, and prints the verdict for the writer agent.

Usage:
    python3 verify-section-refs.py \
        --content-file /tmp/section-developers-ARCH-data-model.md \
        --refs-file /tmp/refs-developers-ARCH-data-model.json \
        --verifier-prompt agents/section-verifier.md \
        --log-file /tmp/verification-log.json

Exit 0 always (verification results are data, not errors).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def derive_section(content_file):
    """Extract DOCUMENT/section-slug from content filename.

    Expected pattern: section-{audience}-{DOCUMENT}-{section-slug}.md
    Returns "{DOCUMENT}/{section-slug}" or the basename as fallback.
    """
    basename = os.path.basename(content_file)
    # Strip .md extension
    name = basename.removesuffix(".md")
    # Pattern: section-{audience}-{DOCUMENT}-{section-slug}
    m = re.match(r"^section-[^-]+-([^-]+)-(.+)$", name)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return name


def append_log_entry(log_file, entry):
    """Append an entry to the JSON array log file."""
    existing = load_json(log_file, default=[])
    existing.append(entry)
    save_json(log_file, existing)


def main():
    parser = argparse.ArgumentParser(
        description="Verify section references via claude CLI"
    )
    parser.add_argument(
        "--content-file", required=True,
        help="Path to section markdown file",
    )
    parser.add_argument(
        "--refs-file", required=True,
        help="Path to section refs JSON file",
    )
    parser.add_argument(
        "--verifier-prompt", required=True,
        help="Path to section-verifier.md prompt file",
    )
    parser.add_argument(
        "--log-file", required=True,
        help="Path to verification log JSON file (appended to)",
    )
    args = parser.parse_args()

    section = derive_section(args.content_file)

    # Check if refs have anything to verify
    refs = load_json(args.refs_file, default={})
    symbols = refs.get("symbols", [])
    file_paths = refs.get("file_paths", [])

    if not symbols and not file_paths:
        entry = {
            "section": section,
            "result": "SKIP",
            "unresolved": [],
            "raw_output": "no refs to verify",
            "duration_ms": 0,
            "cost_usd": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — no refs to verify")
        return

    # Check claude CLI availability
    if not shutil.which("claude"):
        entry = {
            "section": section,
            "result": "SKIP",
            "unresolved": [],
            "raw_output": "claude CLI not available",
            "duration_ms": 0,
            "cost_usd": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — claude CLI not available")
        return

    # Build prompt
    try:
        with open(args.verifier_prompt, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    except OSError as e:
        entry = {
            "section": section,
            "result": "ERROR",
            "unresolved": [],
            "raw_output": f"cannot read verifier prompt: {e}",
            "duration_ms": 0,
            "cost_usd": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — verification failed")
        return

    full_prompt = (
        f"{prompt_text}\n\n"
        f"Content file: {args.content_file}\n"
        f"Refs file: {args.refs_file}"
    )

    # Invoke claude -p
    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--model", "haiku",
                "--allowed-tools", "Read",
                "--output-format", "json",
            ],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        entry = {
            "section": section,
            "result": "SKIP",
            "unresolved": [],
            "raw_output": "claude CLI not found",
            "duration_ms": 0,
            "cost_usd": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — claude CLI not available")
        return
    except subprocess.TimeoutExpired:
        entry = {
            "section": section,
            "result": "ERROR",
            "unresolved": [],
            "raw_output": "claude CLI timed out after 120s",
            "duration_ms": 120000,
            "cost_usd": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — verification failed")
        return

    # Parse JSON response
    try:
        response = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        entry = {
            "section": section,
            "result": "ERROR",
            "unresolved": [],
            "raw_output": result.stdout[:500] if result.stdout else result.stderr[:500],
            "duration_ms": 0,
            "cost_usd": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — verification failed")
        return

    # Extract fields from response
    is_error = response.get("is_error", False)
    raw_output = response.get("result", "")
    duration_ms = response.get("duration_ms", 0)
    cost_usd = response.get("total_cost_usd", 0)
    usage = response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    if result.returncode != 0 or is_error:
        entry = {
            "section": section,
            "result": "ERROR",
            "unresolved": [],
            "raw_output": raw_output,
            "duration_ms": duration_ms,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        append_log_entry(args.log_file, entry)
        print("SKIP — verification failed")
        return

    # Parse result text for PASS/UNRESOLVED
    unresolved = []
    if "UNRESOLVED" in raw_output:
        verdict = "UNRESOLVED"
        # Extract unresolved items from lines like "- `symbol_name` — ..."
        for line in raw_output.splitlines():
            m = re.match(r"^-\s+`([^`]+)`", line.strip())
            if m:
                unresolved.append(m.group(1))
    else:
        verdict = "PASS"

    entry = {
        "section": section,
        "result": verdict,
        "unresolved": unresolved,
        "raw_output": raw_output,
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    append_log_entry(args.log_file, entry)
    print(raw_output)


if __name__ == "__main__":
    main()
