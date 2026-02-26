#!/usr/bin/env python3
"""Read and update task file status for field-mapping research.

Provides CLI operations to list, read, and update task files without
agents needing to parse/write markdown directly.

All commands accept --work-dir (default: .mg/data-provider). Task files
are resolved relative to <work-dir>/tasks/.

Usage:
    # List all task files filtered by status
    python scripts/field_mapper/status.py list [--status pending]

    # Read a single task file as structured output
    python scripts/field_mapper/status.py read --file field-01-revenue-yoy--simfin.md

    # Update status
    python scripts/field_mapper/status.py update --file <filename> --status researched

    # Set research results
    python scripts/field_mapper/status.py set-research --file <filename> \
        --match-type DERIVABLE \
        --endpoint "GET /api/v3/companies/statements" \
        --endpoint-version "v3" \
        --params '{"statement": "pl", "period": "quarterly"}' \
        --json-path "$.revenue" \
        --derivation-formula "((sum Q1-Q4) - (sum Q1'-Q4')) / (sum Q1'-Q4')" \
        --evidence-url "https://example.com/docs" \
        --api-version-confirmed "yes" \
        --example-response "{'revenue': 123456}" \
        --historical-depth "2010+" \
        --notes "Quarterly data available"

    # Set verification results
    python scripts/field_mapper/status.py set-verification --file <filename> \
        --verified true \
        --endpoint-exists true \
        --field-in-response true \
        --derivation-correct true \
        --historical-available true \
        --api-version-current true \
        --rejection-reason ""

    # Increment iterations (used on rejection)
    python scripts/field_mapper/status.py increment-iterations --file <filename>

    # Clear research and verification sections (for retry)
    python scripts/field_mapper/status.py clear-research --file <filename>
"""

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_WORK_DIR = ".mg/data-provider"


def parse_task_file(filepath: Path) -> dict[str, dict[str, str]]:
    """Parse a task file into sections with key-value pairs.

    Returns a dict of sections, each containing key-value pairs.
    Handles multiline values (lines starting with '>') and indented sub-keys.
    """
    content = filepath.read_text()
    sections: dict[str, dict[str, str]] = {}
    current_section = ""
    current_key = ""

    for line in content.splitlines():
        # Section header: ## Config, ## Research, ## Verification
        section_match = re.match(r"^## (.+)$", line)
        if section_match:
            current_section = section_match.group(1).strip()
            sections[current_section] = {}
            current_key = ""
            continue

        if not current_section:
            continue

        # Skip title line and empty lines
        if line.startswith("# ") or not line.strip():
            continue

        # Indented sub-key (e.g., "  endpoint_exists: true" under checks:)
        indent_match = re.match(r"^  (\w[\w_]*): ?(.*)$", line)
        if indent_match:
            sub_key = indent_match.group(1)
            sub_val = indent_match.group(2).strip()
            sections[current_section][sub_key] = sub_val
            current_key = sub_key
            continue

        # Top-level key-value
        kv_match = re.match(r"^(\w[\w_]*): ?(.*)$", line)
        if kv_match:
            key = kv_match.group(1)
            val = kv_match.group(2).strip()
            # Handle multiline indicator '>'
            if val == ">":
                val = ""
            sections[current_section][key] = val
            current_key = key
            continue

        # Continuation line for multiline values
        if current_key and line.startswith("  "):
            existing = sections[current_section].get(current_key, "")
            addition = line.strip()
            if existing:
                sections[current_section][current_key] = existing + " " + addition
            else:
                sections[current_section][current_key] = addition

    return sections


def update_field_in_file(filepath: Path, section: str, key: str, value: str) -> None:
    """Update a single key-value pair in a task file, preserving structure."""
    lines = filepath.read_text().splitlines()
    in_section = False
    in_checks = False
    updated = False

    for i, line in enumerate(lines):
        section_match = re.match(r"^## (.+)$", line)
        if section_match:
            in_section = section_match.group(1).strip() == section
            in_checks = False
            continue

        if not in_section:
            continue

        # Handle indented keys under 'checks:'
        if line.strip() == "checks:":
            in_checks = True
            continue

        if in_checks:
            indent_match = re.match(r"^(  )(\w[\w_]*): ?(.*)$", line)
            if indent_match and indent_match.group(2) == key:
                lines[i] = f"  {key}: {value}"
                updated = True
                break
            # End of checks block (non-indented line with content)
            if line.strip() and not line.startswith("  "):
                in_checks = False

        # Top-level key match
        kv_match = re.match(r"^(\w[\w_]*): ?(.*)$", line)
        if kv_match and kv_match.group(1) == key:
            # Check if next line is a multiline continuation
            if kv_match.group(2).strip() == ">":
                # Replace the '>' line and the continuation
                lines[i] = f"{key}: {value}"
                # Remove continuation lines
                while i + 1 < len(lines) and lines[i + 1].startswith("  "):
                    lines.pop(i + 1)
            else:
                lines[i] = f"{key}: {value}"
            updated = True
            break

    if updated:
        filepath.write_text("\n".join(lines) + "\n")
    else:
        print(
            f"Warning: key '{key}' not found in section '{section}' of {filepath.name}",
            file=sys.stderr,
        )


def resolve_file(args: argparse.Namespace) -> Path:
    """Resolve a task filename to its full path under <work-dir>/tasks/."""
    tasks_dir = Path(args.work_dir) / "tasks"
    filepath = Path(args.file)
    # If already absolute or contains the tasks dir, use as-is
    if filepath.is_absolute():
        return filepath
    # Otherwise resolve relative to tasks dir
    return tasks_dir / filepath


def cmd_list(args: argparse.Namespace) -> None:
    """List task files, optionally filtered by status."""
    tasks_dir = Path(args.work_dir) / "tasks"
    if not tasks_dir.exists():
        print(f"Error: Tasks directory not found: {tasks_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(tasks_dir.glob("field-*.md"))
    results = []

    for f in files:
        sections = parse_task_file(f)
        config = sections.get("Config", {})
        status = config.get("status", "unknown")
        iterations = config.get("iterations", "0")

        if args.status and status != args.status:
            continue

        results.append(
            {
                "file": f.name,
                "field_number": config.get("field_number", "?"),
                "field_name": config.get("field_name", "?"),
                "provider": config.get("provider", "?"),
                "status": status,
                "iterations": iterations,
            }
        )

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(
                f"[{r['status']:>12}] (iter={r['iterations']}) "
                f"{r['file']}"
            )

    if not results:
        print("No matching task files found.", file=sys.stderr)


def cmd_read(args: argparse.Namespace) -> None:
    """Read and display a single task file as structured output."""
    filepath = resolve_file(args)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    sections = parse_task_file(filepath)
    print(json.dumps(sections, indent=2))


def cmd_update(args: argparse.Namespace) -> None:
    """Update the status field of a task file."""
    filepath = resolve_file(args)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    valid_statuses = ["pending", "researched", "verified", "inconclusive"]
    if args.status not in valid_statuses:
        print(
            f"Error: Invalid status '{args.status}'. Must be one of: {valid_statuses}",
            file=sys.stderr,
        )
        sys.exit(1)

    update_field_in_file(filepath, "Config", "status", args.status)
    print(f"Updated {filepath.name}: status → {args.status}")


def cmd_set_research(args: argparse.Namespace) -> None:
    """Set research results in a task file."""
    filepath = resolve_file(args)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    field_map = {
        "match_type": args.match_type,
        "endpoint": args.endpoint or "",
        "endpoint_version": args.endpoint_version or "",
        "params": args.params or "",
        "json_path": args.json_path or "",
        "derivation_formula": args.derivation_formula or "",
        "evidence_url": args.evidence_url or "",
        "api_version_confirmed": args.api_version_confirmed or "",
        "example_response_snippet": args.example_response or "",
        "historical_depth": args.historical_depth or "",
        "notes": args.notes or "",
    }

    for key, value in field_map.items():
        update_field_in_file(filepath, "Research", key, value)

    # Also update status to researched
    update_field_in_file(filepath, "Config", "status", "researched")
    print(f"Updated {filepath.name}: research results set, status → researched")


def cmd_set_verification(args: argparse.Namespace) -> None:
    """Set verification results in a task file."""
    filepath = resolve_file(args)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    update_field_in_file(filepath, "Verification", "verified", args.verified)
    update_field_in_file(
        filepath, "Verification", "endpoint_exists", args.endpoint_exists or ""
    )
    update_field_in_file(
        filepath, "Verification", "field_in_response", args.field_in_response or ""
    )
    update_field_in_file(
        filepath, "Verification", "derivation_correct", args.derivation_correct or ""
    )
    update_field_in_file(
        filepath,
        "Verification",
        "historical_available",
        args.historical_available or "",
    )
    update_field_in_file(
        filepath, "Verification", "api_version_current", args.api_version_current or ""
    )
    update_field_in_file(
        filepath, "Verification", "rejection_reason", args.rejection_reason or ""
    )

    # Update status based on verification outcome
    if args.verified == "true":
        update_field_in_file(filepath, "Config", "status", "verified")
        print(f"Updated {filepath.name}: verified, status → verified")
    else:
        # Check iterations to decide if inconclusive or retry
        sections = parse_task_file(filepath)
        iterations = int(sections.get("Config", {}).get("iterations", "0"))
        if iterations >= 1:
            update_field_in_file(filepath, "Config", "status", "inconclusive")
            print(f"Updated {filepath.name}: rejected, iterations={iterations}, status → inconclusive")
        else:
            update_field_in_file(filepath, "Config", "status", "pending")
            print(f"Updated {filepath.name}: rejected, status → pending (ready for retry)")

    print(f"Verification results written to {filepath.name}")


def cmd_increment_iterations(args: argparse.Namespace) -> None:
    """Increment the iteration counter of a task file."""
    filepath = resolve_file(args)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    sections = parse_task_file(filepath)
    current = int(sections.get("Config", {}).get("iterations", "0"))
    new_val = current + 1
    update_field_in_file(filepath, "Config", "iterations", str(new_val))
    print(f"Updated {filepath.name}: iterations {current} → {new_val}")


def cmd_clear_research(args: argparse.Namespace) -> None:
    """Clear research and verification sections for retry."""
    filepath = resolve_file(args)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    research_fields = [
        "match_type",
        "endpoint",
        "endpoint_version",
        "params",
        "json_path",
        "derivation_formula",
        "evidence_url",
        "api_version_confirmed",
        "example_response_snippet",
        "historical_depth",
        "notes",
    ]
    verification_fields = [
        "verified",
        "endpoint_exists",
        "field_in_response",
        "derivation_correct",
        "historical_available",
        "api_version_current",
        "rejection_reason",
    ]

    for key in research_fields:
        update_field_in_file(filepath, "Research", key, "")
    for key in verification_fields:
        update_field_in_file(filepath, "Verification", key, "")

    print(f"Cleared research and verification sections in {filepath.name}")


def add_work_dir_arg(parser: argparse.ArgumentParser) -> None:
    """Add the --work-dir argument to a parser."""
    parser.add_argument(
        "--work-dir",
        default=DEFAULT_WORK_DIR,
        help=f"Work directory (default: {DEFAULT_WORK_DIR})",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage field-mapping task file status."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List task files by status")
    add_work_dir_arg(p_list)
    p_list.add_argument(
        "--status",
        choices=["pending", "researched", "verified", "inconclusive"],
        help="Filter by status",
    )
    p_list.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    # read
    p_read = subparsers.add_parser("read", help="Read a task file")
    add_work_dir_arg(p_read)
    p_read.add_argument("--file", required=True, help="Task filename")

    # update
    p_update = subparsers.add_parser("update", help="Update task status")
    add_work_dir_arg(p_update)
    p_update.add_argument("--file", required=True, help="Task filename")
    p_update.add_argument("--status", required=True, help="New status")

    # set-research
    p_research = subparsers.add_parser(
        "set-research", help="Set research results"
    )
    add_work_dir_arg(p_research)
    p_research.add_argument("--file", required=True, help="Task filename")
    p_research.add_argument(
        "--match-type",
        required=True,
        choices=["DIRECT", "DERIVABLE", "NONE"],
    )
    p_research.add_argument("--endpoint", default="")
    p_research.add_argument("--endpoint-version", default="")
    p_research.add_argument("--params", default="")
    p_research.add_argument("--json-path", default="")
    p_research.add_argument("--derivation-formula", default="")
    p_research.add_argument("--evidence-url", default="")
    p_research.add_argument("--api-version-confirmed", default="")
    p_research.add_argument("--example-response", default="")
    p_research.add_argument("--historical-depth", default="")
    p_research.add_argument("--notes", default="")

    # set-verification
    p_verify = subparsers.add_parser(
        "set-verification", help="Set verification results"
    )
    add_work_dir_arg(p_verify)
    p_verify.add_argument("--file", required=True, help="Task filename")
    p_verify.add_argument(
        "--verified", required=True, choices=["true", "false"]
    )
    p_verify.add_argument("--endpoint-exists", default="")
    p_verify.add_argument("--field-in-response", default="")
    p_verify.add_argument("--derivation-correct", default="")
    p_verify.add_argument("--historical-available", default="")
    p_verify.add_argument("--api-version-current", default="")
    p_verify.add_argument("--rejection-reason", default="")

    # increment-iterations
    p_inc = subparsers.add_parser(
        "increment-iterations", help="Increment iteration counter"
    )
    add_work_dir_arg(p_inc)
    p_inc.add_argument("--file", required=True, help="Task filename")

    # clear-research
    p_clear = subparsers.add_parser(
        "clear-research", help="Clear research+verification for retry"
    )
    add_work_dir_arg(p_clear)
    p_clear.add_argument("--file", required=True, help="Task filename")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "read": cmd_read,
        "update": cmd_update,
        "set-research": cmd_set_research,
        "set-verification": cmd_set_verification,
        "increment-iterations": cmd_increment_iterations,
        "clear-research": cmd_clear_research,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
