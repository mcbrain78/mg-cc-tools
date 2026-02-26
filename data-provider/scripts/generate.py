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


def parse_fields_yaml(field_ref_path: Path) -> list[dict]:
    """Parse the fields.yaml reference file.

    Handles the subset of YAML used here: a top-level ``fields:`` key
    containing a list of mappings with scalar string values.  Supports
    ``#`` comments, blank lines, and double-quoted values.

    Returns a list of dicts with keys: number, name, category,
    definition, derivation_inputs.
    """
    fields: list[dict] = []
    current: dict | None = None

    for raw_line in field_ref_path.read_text().splitlines():
        # Strip inline comments (only outside quotes)
        line = raw_line.split(" #")[0] if " #" in raw_line and '"' not in raw_line else raw_line
        stripped = line.strip()

        # Skip blank lines and full-line comments
        if not stripped or stripped.startswith("#"):
            continue

        # Skip the top-level "fields:" key
        if stripped == "fields:":
            continue

        # List item start: "  - key: value"
        list_match = re.match(r"^\s*-\s+(\w[\w\s]*?):\s*(.*?)\s*$", line)
        if list_match:
            if current is not None:
                fields.append(current)
            current = {"number": 0, "name": "", "category": "", "definition": "", "derivation_inputs": ""}
            key = list_match.group(1).strip()
            val = _unquote(list_match.group(2))
            current[key] = int(val) if key == "number" else val
            continue

        # Continuation key: "    key: value"
        kv_match = re.match(r"^\s+(\w[\w\s]*?):\s*(.*?)\s*$", line)
        if kv_match and current is not None:
            key = kv_match.group(1).strip()
            val = _unquote(kv_match.group(2))
            current[key] = int(val) if key == "number" else val

    if current is not None:
        fields.append(current)

    return fields


def _unquote(val: str) -> str:
    """Strip surrounding double quotes from a value."""
    if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    return val


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
field_category: {field['category']}
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
    field_ref = input_dir / "fields.yaml"
    providers_file = input_dir / "providers.txt"

    if not field_ref.exists():
        print(f"Error: Field reference not found: {field_ref}", file=sys.stderr)
        sys.exit(1)

    if not providers_file.exists():
        print(f"Error: Provider list not found: {providers_file}", file=sys.stderr)
        sys.exit(1)

    tasks_dir.mkdir(parents=True, exist_ok=True)

    fields = parse_fields_yaml(field_ref)
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
