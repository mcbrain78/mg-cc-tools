#!/usr/bin/env python3
"""Generate task files for field-provider mapping research.

Reads the field reference and provider list from the work directory's
input/ folder, then creates one task file per (field, provider) combination
in the tasks/ folder.

Usage:
    python scripts/field_mapper/generate.py
    python scripts/field_mapper/generate.py --work-dir .mg/data-provider --model opus
    python scripts/field_mapper/generate.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_WORK_DIR = ".mg/data-provider"


def slugify(name: str) -> str:
    """Convert a display name to a kebab-case slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_fields(field_ref_path: Path) -> list[dict]:
    """Parse the field reference markdown to extract field definitions.

    Returns a list of dicts with keys: number, name, definition, derivation_inputs.
    """
    content = field_ref_path.read_text()

    # Parse the fields table rows: | # | `Field Name` | Definition |
    field_pattern = re.compile(
        r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|$", re.MULTILINE
    )
    fields = []
    for match in field_pattern.finditer(content):
        fields.append(
            {
                "number": int(match.group(1)),
                "name": match.group(2),
                "definition": match.group(3).strip(),
                "derivation_inputs": "",
            }
        )

    # Parse the substitutions table: | `Field Name` (#N) | Raw Inputs Needed |
    sub_pattern = re.compile(
        r"^\|\s*`([^`]+)`\s*\(#(\d+)\)\s*\|\s*(.+?)\s*\|$", re.MULTILINE
    )
    sub_map = {}
    for match in sub_pattern.finditer(content):
        sub_map[int(match.group(2))] = match.group(3).strip()

    for field in fields:
        field["derivation_inputs"] = sub_map.get(field["number"], "")

    return fields


def parse_providers(providers_path: Path) -> list[str]:
    """Read provider names from providers.txt (one per line, skip blanks)."""
    lines = providers_path.read_text().splitlines()
    return [line.strip() for line in lines if line.strip()]


def generate_task_file(
    field: dict, provider_name: str, provider_slug: str, model: str
) -> str:
    """Generate the markdown content for a single task file."""
    return f"""# Task: {field['name']} → {provider_name}

## Config
field_number: {field['number']}
field_name: {field['name']}
field_definition: >
  {field['definition']}
derivation_inputs: {field['derivation_inputs']}
provider: {provider_name}
provider_slug: {provider_slug}
model: {model}
status: pending
iterations: 0

## Research
match_type:
endpoint:
endpoint_version:
params:
json_path:
derivation_formula:
evidence_url:
api_version_confirmed:
example_response_snippet: >

historical_depth:
notes:

## Verification
verified:
checks:
  endpoint_exists:
  field_in_response:
  derivation_correct:
  historical_available:
  api_version_current:
rejection_reason:
"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate field-mapping task files for provider research."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help=f"Work directory (default: {DEFAULT_WORK_DIR})",
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        choices=["sonnet", "opus", "haiku"],
        help="Model to use for research agents (default: sonnet)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without writing files",
    )

    args = parser.parse_args()

    input_dir = args.work_dir / "input"
    tasks_dir = args.work_dir / "tasks"
    field_ref = input_dir / "00-field-reference.md"
    providers_file = input_dir / "providers.txt"

    if not field_ref.exists():
        print(f"Error: Field reference not found: {field_ref}", file=sys.stderr)
        sys.exit(1)

    if not providers_file.exists():
        print(f"Error: Provider list not found: {providers_file}", file=sys.stderr)
        sys.exit(1)

    tasks_dir.mkdir(parents=True, exist_ok=True)

    fields = parse_fields(field_ref)
    if not fields:
        print("Error: No fields parsed from field reference.", file=sys.stderr)
        sys.exit(1)

    providers = parse_providers(providers_file)
    if not providers:
        print("Error: No providers found in providers.txt.", file=sys.stderr)
        sys.exit(1)

    created = 0
    skipped = 0

    for field in fields:
        field_slug = slugify(field["name"])
        for provider_name in providers:
            provider_slug = slugify(provider_name)
            filename = f"field-{field['number']:02d}-{field_slug}--{provider_slug}.md"
            filepath = tasks_dir / filename

            if args.dry_run:
                exists = filepath.exists()
                tag = "EXISTS" if exists else "CREATE"
                print(f"  [{tag}] {filename}")
                if exists:
                    skipped += 1
                else:
                    created += 1
                continue

            if filepath.exists():
                skipped += 1
                continue

            content = generate_task_file(
                field, provider_name, provider_slug, args.model
            )
            filepath.write_text(content)
            created += 1

    total = len(fields) * len(providers)
    print(f"Fields: {len(fields)}, Providers: {len(providers)}, Total: {total}")
    print(f"Created: {created}, Skipped (already exist): {skipped}")


if __name__ == "__main__":
    main()
