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
from lib.db_format import slice_and_format
from lib.json_io import load_json


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

    output = slice_and_format(model, requested)

    # Check for missing tables and warn
    requested_set = set(requested)
    found = set()
    for schema_data in model["schemas"].values():
        for table_name in schema_data.get("tables", {}):
            if table_name in requested_set:
                found.add(table_name)
    for table in requested:
        if table not in found:
            print(f"Warning: table '{table}' not found in database model", file=sys.stderr)

    if output:
        print(output)


if __name__ == "__main__":
    main()
