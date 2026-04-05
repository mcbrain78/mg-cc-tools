#!/usr/bin/env python3
"""Slice reader for database-model.json.

Filters to requested tables and outputs compact column detail to stdout.
Called by writer agents during orient blocks with relevant_tables.

Usage:
    python3 read-database-model.py --db-model PATH --tables t1,t2,t3
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json


def format_table(schema_name, table_name, table_data):
    """Format a single table as compact text."""
    lines = [f"{schema_name}.{table_name}:"]
    for col in table_data["columns"]:
        parts = [f"  {col['name']}: {col['type']}"]
        if col.get("primary_key"):
            parts.append("PK")
        if not col.get("nullable", True) and not col.get("primary_key"):
            parts.append("NOT NULL")
        if col.get("foreign_key"):
            parts.append(f"FK({col['foreign_key']})")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Slice reader for database-model.json")
    parser.add_argument("--db-model", required=True, help="Path to database-model.json")
    parser.add_argument("--tables", required=True, help="Comma-separated table names to extract")
    args = parser.parse_args()

    requested = [t.strip() for t in args.tables.split(",") if t.strip()]
    if not requested:
        return

    model = load_json(os.path.abspath(args.db_model))
    if not model or not model.get("schemas"):
        print("Warning: no schemas in database model", file=sys.stderr)
        return

    requested_set = set(requested)
    found = set()
    blocks = []

    for schema_name, schema_data in model["schemas"].items():
        for table_name, table_data in schema_data.get("tables", {}).items():
            if table_name in requested_set:
                found.add(table_name)
                blocks.append(format_table(schema_name, table_name, table_data))

    for table in requested:
        if table not in found:
            print(f"Warning: table '{table}' not found in database model", file=sys.stderr)

    if blocks:
        print("\n\n".join(blocks))


if __name__ == "__main__":
    main()
