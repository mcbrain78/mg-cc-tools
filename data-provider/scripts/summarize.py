#!/usr/bin/env python3
"""Summarize field-mapping task files into a coverage report.

Reads all task files from <work-dir>/tasks/ and produces a markdown
coverage report in <work-dir>/output/coverage-report.md.

Usage:
    python scripts/field_mapper/summarize.py
    python scripts/field_mapper/summarize.py --work-dir .mg/data-provider
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the parser from status.py
sys.path.insert(0, str(Path(__file__).parent))
from status import parse_task_file

DEFAULT_WORK_DIR = ".mg/data-provider"


def collect_tasks(tasks_dir: Path) -> list[dict[str, str]]:
    """Collect and parse all task files into a flat list of records."""
    records = []
    for filepath in sorted(tasks_dir.glob("field-*.md")):
        sections = parse_task_file(filepath)
        config = sections.get("Config", {})
        research = sections.get("Research", {})
        verification = sections.get("Verification", {})

        records.append(
            {
                "file": filepath.name,
                "field_number": config.get("field_number", "0"),
                "field_name": config.get("field_name", "?"),
                "provider": config.get("provider", "?"),
                "status": config.get("status", "unknown"),
                "iterations": config.get("iterations", "0"),
                "match_type": research.get("match_type", ""),
                "endpoint": research.get("endpoint", ""),
                "endpoint_version": research.get("endpoint_version", ""),
                "json_path": research.get("json_path", ""),
                "evidence_url": research.get("evidence_url", ""),
                "derivation_formula": research.get("derivation_formula", ""),
                "historical_depth": research.get("historical_depth", ""),
                "notes": research.get("notes", ""),
                "verified": verification.get("verified", ""),
                "rejection_reason": verification.get("rejection_reason", ""),
            }
        )

    return records


def build_coverage_matrix(
    records: list[dict[str, str]],
    fields: list[tuple[str, str]],
    providers: list[str],
) -> str:
    """Build the coverage matrix table."""
    # Index: (field_number, provider) → match_type
    lookup: dict[tuple[str, str], str] = {}
    for r in records:
        key = (r["field_number"], r["provider"])
        if r["status"] == "verified":
            lookup[key] = r["match_type"]
        elif r["status"] == "inconclusive":
            lookup[key] = "INCONCLUSIVE"
        elif r["status"] == "pending":
            lookup[key] = "PENDING"
        else:
            lookup[key] = r.get("match_type", "?")

    # Header
    header = "| # | Field |"
    sep = "|---|-------|"
    for p in providers:
        header += f" {p} |"
        sep += "------|"

    lines = [header, sep]

    for field_num, field_name in fields:
        row = f"| {field_num} | {field_name} |"
        for p in providers:
            val = lookup.get((field_num, p), "-")
            row += f" {val} |"
        lines.append(row)

    # Totals row
    totals_row = "| | **Coverage** |"
    for p in providers:
        direct = sum(
            1
            for fn, _ in fields
            if lookup.get((fn, p), "") in ("DIRECT", "DERIVABLE")
        )
        total = len(fields)
        totals_row += f" **{direct}/{total}** |"
    lines.append(totals_row)

    return "\n".join(lines)


def build_field_details(
    records: list[dict[str, str]],
    fields: list[tuple[str, str]],
) -> str:
    """Build per-field detail tables."""
    # Group records by field number
    by_field: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in records:
        by_field[r["field_number"]].append(r)

    sections = []

    for field_num, field_name in fields:
        field_records = by_field.get(field_num, [])
        if not field_records:
            continue

        # Only include fields that have at least one processed result
        processed = [
            r
            for r in field_records
            if r["status"] in ("verified", "inconclusive", "researched")
        ]
        if not processed:
            continue

        lines = [
            f"### {field_num}. {field_name}",
            "",
            "| Provider | Match | Endpoint | Field/Path | Derivation | Docs |",
            "|----------|-------|----------|-----------|------------|------|",
        ]

        for r in processed:

            match = r["match_type"] or "-"
            endpoint = f"`{r['endpoint']}`" if r["endpoint"] else "-"
            json_path = f"`{r['json_path']}`" if r["json_path"] else "-"
            derivation = r["derivation_formula"] or "-"
            evidence = f"[docs]({r['evidence_url']})" if r["evidence_url"] else "-"

            lines.append(
                f"| {r['provider']} | {match} | {endpoint} | {json_path} | {derivation} | {evidence} |"
            )

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def build_inconclusive_section(records: list[dict[str, str]]) -> str:
    """Build the inconclusive items section."""
    inconclusive = [r for r in records if r["status"] == "inconclusive"]
    if not inconclusive:
        return "No inconclusive items."

    lines = [
        "| # | Field | Provider | Last Rejection Reason |",
        "|---|-------|----------|----------------------|",
    ]

    for r in sorted(inconclusive, key=lambda x: (x["field_number"], x["provider"])):
        reason = r["rejection_reason"] or "No reason recorded"
        lines.append(
            f"| {r['field_number']} | {r['field_name']} | {r['provider']} | {reason} |"
        )

    return "\n".join(lines)


def build_pending_section(records: list[dict[str, str]]) -> str:
    """Build the pending items section."""
    pending = [r for r in records if r["status"] == "pending"]
    if not pending:
        return "All tasks processed."

    return f"{len(pending)} task(s) still pending. Run `/mg:map-fields-research` to process them."


def generate_report(tasks_dir: Path) -> str:
    """Generate the full coverage report."""
    records = collect_tasks(tasks_dir)

    if not records:
        return "# Provider Coverage Report\n\nNo task files found."

    # Extract unique fields and providers (ordered)
    fields_seen: dict[str, str] = {}
    providers_seen: dict[str, bool] = {}
    for r in records:
        fields_seen[r["field_number"]] = r["field_name"]
        providers_seen[r["provider"]] = True

    fields = sorted(fields_seen.items(), key=lambda x: int(x[0]))
    providers = list(providers_seen.keys())

    # Count stats
    total = len(records)
    verified = sum(1 for r in records if r["status"] == "verified")
    inconclusive = sum(1 for r in records if r["status"] == "inconclusive")
    pending = sum(1 for r in records if r["status"] == "pending")

    report = f"""# Provider Coverage Report

Generated from: `{tasks_dir}`

**Status:** {verified} verified | {inconclusive} inconclusive | {pending} pending | {total} total

---

## Coverage Matrix

{build_coverage_matrix(records, fields, providers)}

---

## Field Details

{build_field_details(records, fields)}

---

## Inconclusive (manual review needed)

{build_inconclusive_section(records)}

---

## Pending

{build_pending_section(records)}
"""

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate coverage report from field-mapping task files."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help=f"Work directory (default: {DEFAULT_WORK_DIR})",
    )

    args = parser.parse_args()

    tasks_dir = args.work_dir / "tasks"
    output_dir = args.work_dir / "output"
    output_file = output_dir / "coverage-report.md"

    if not tasks_dir.exists():
        print(f"Error: Tasks directory not found: {tasks_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    report = generate_report(tasks_dir)
    output_file.write_text(report)
    print(f"Report written to: {output_file}")


if __name__ == "__main__":
    main()
