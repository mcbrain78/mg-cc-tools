#!/usr/bin/env python3
"""Deterministic database model extraction from SQLAlchemy metadata.

Imports SQLAlchemy model files from the target project, discovers
DeclarativeBase subclasses, and walks Base.metadata.sorted_tables to
produce a structured JSON file with correct schema -> table -> column
mappings.

Runs in the TARGET project's Python env (not mg-cc-tools'). Invoked via
``uv run --directory {project_root}`` from generate-setup.py.

Usage:
    uv run python3 extract-database-model.py \
        --project-root /path/to/project \
        --search-paths src/road_runner/db,src/road_runner \
        --project-model /path/to/project-model.json \
        --output /path/to/database-model.json
"""

import argparse
import datetime
import importlib
import importlib.util
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def _skip(output_path, reason):
    """Write a skip marker and exit 0."""
    save_json(output_path, {"extraction": "skipped", "reason": reason})
    print(f"Skipped: {reason}", file=sys.stderr)


def _is_sqlalchemy(project_model):
    """Check if the project uses SQLAlchemy based on project_model.database."""
    db = project_model.get("database")
    if not db:
        return False
    orm = str(db.get("orm", db.get("orm_framework", ""))).lower()
    return "sqlalchemy" in orm


def _find_python_files(project_root, search_paths):
    """Recursively find .py files under each search path."""
    files = []
    for search_path in search_paths:
        abs_path = os.path.join(project_root, search_path)
        if not os.path.isdir(abs_path):
            print(f"Warning: search path not found: {search_path}", file=sys.stderr)
            continue
        for dirpath, _dirnames, filenames in os.walk(abs_path):
            for fname in filenames:
                if fname.endswith(".py") and not fname.startswith("__"):
                    files.append(os.path.join(dirpath, fname))
    return files


def _discover_bases(project_root, python_files):
    """Import each file and discover SQLAlchemy DeclarativeBase subclasses.

    Returns a list of unique MetaData objects with populated tables.
    """
    # Ensure project root is on sys.path for imports
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from sqlalchemy.orm import DeclarativeBase, DeclarativeBaseNoMeta
    except ImportError:
        try:
            from sqlalchemy.ext.declarative import declarative_base  # noqa: F401
            DeclarativeBase = None
            DeclarativeBaseNoMeta = None
        except ImportError:
            return []

    metadata_map = {}  # id(MetaData) -> MetaData

    def _register(meta):
        if meta is not None and hasattr(meta, "sorted_tables"):
            metadata_map[id(meta)] = meta

    for fpath in python_files:
        # Build a module name from the file path
        rel = os.path.relpath(fpath, project_root)
        mod_name = rel.replace(os.sep, ".").removesuffix(".py")

        # Skip already-imported modules to avoid double-import issues
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            spec = importlib.util.spec_from_file_location(mod_name, fpath)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception:
                print(
                    f"Warning: failed to import {rel}: "
                    f"{traceback.format_exc().splitlines()[-1]}",
                    file=sys.stderr,
                )
                del sys.modules[mod_name]
                continue

        # Inspect module namespace for Base classes
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if obj is None or not isinstance(obj, type):
                continue

            # SQLAlchemy 2.0+ DeclarativeBase
            if DeclarativeBase is not None and issubclass(obj, DeclarativeBase):
                _register(getattr(obj, "metadata", None))

            if DeclarativeBaseNoMeta is not None and issubclass(obj, DeclarativeBaseNoMeta):
                _register(getattr(obj, "metadata", None))

            # SQLAlchemy 1.x model classes with __tablename__
            if hasattr(obj, "metadata") and hasattr(obj, "__tablename__"):
                _register(getattr(obj, "metadata", None))

    return list(metadata_map.values())


def _build_summary(schemas):
    """Build compact summary with column counts and FK targets per table."""
    summary = {}
    for schema_name, schema_data in schemas.items():
        summary[schema_name] = {"tables": {}}
        for table_name, table_data in schema_data["tables"].items():
            columns = table_data["columns"]
            fks = []
            for col in columns:
                if col["foreign_key"]:
                    fks.append(col["foreign_key"])
            summary[schema_name]["tables"][table_name] = {
                "columns": len(columns),
                "fks": fks,
            }
    return summary


def _extract_schemas(metadata_list):
    """Walk sorted_tables from all metadata objects, build schema dict.

    Returns dict of schema_name -> {tables: {table_name -> {columns: [...]}}}
    """
    schemas = {}

    # Collect all tables across all metadata, deduplicate by identity
    seen_tables = set()
    all_tables = []
    for metadata in metadata_list:
        for table in metadata.sorted_tables:
            if id(table) not in seen_tables:
                seen_tables.add(id(table))
                all_tables.append(table)

    for table in all_tables:
        schema_name = table.schema if table.schema else "public"
        table_name = table.name

        columns = []
        for col in table.columns:
            fk_target = None
            if col.foreign_keys:
                fk = next(iter(col.foreign_keys))
                fk_target = fk.target_fullname

            columns.append({
                "name": col.name,
                "type": str(col.type),
                "primary_key": col.primary_key,
                "nullable": col.nullable if not col.primary_key else False,
                "foreign_key": fk_target,
            })

        if schema_name not in schemas:
            schemas[schema_name] = {"tables": {}}
        schemas[schema_name]["tables"][table_name] = {"columns": columns}

    return schemas


def main():
    parser = argparse.ArgumentParser(
        description="Extract database model from SQLAlchemy metadata"
    )
    parser.add_argument(
        "--project-root", required=True,
        help="Absolute path to the target project root",
    )
    parser.add_argument(
        "--search-paths", required=True,
        help="Comma-separated relative directories to search for model files",
    )
    parser.add_argument(
        "--project-model", required=True,
        help="Path to project-model.json (for ORM detection and metadata)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write database-model.json",
    )
    parser.add_argument(
        "--summary-output",
        help="Optional path to write compact summary JSON",
    )

    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    output_path = os.path.abspath(args.output)
    search_paths = [p.strip() for p in args.search_paths.split(",") if p.strip()]

    # Load project model
    pm = load_json(os.path.abspath(args.project_model))
    if pm is None:
        _skip(output_path, "project-model.json not found")
        return

    # Check if project uses SQLAlchemy
    if not _is_sqlalchemy(pm):
        _skip(output_path, "project does not use SQLAlchemy")
        return

    # Find Python files
    python_files = _find_python_files(project_root, search_paths)
    if not python_files:
        _skip(output_path, "no Python files found in search paths")
        return

    # Discover Base classes and extract metadata
    metadata_list = _discover_bases(project_root, python_files)
    if not metadata_list:
        _skip(output_path, "no SQLAlchemy DeclarativeBase subclasses found")
        return

    # Extract schemas
    schemas = _extract_schemas(metadata_list)

    # Build output with metadata from project model
    db = pm.get("database", {})
    result = {
        "engine": db.get("engine", None),
        "orm_framework": db.get("orm_framework", db.get("orm", None)),
        "migration_tool": db.get("migration_tool", None),
        "extracted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "schemas": schemas,
    }

    # Write compact summary if requested
    if args.summary_output:
        summary_schemas = _build_summary(schemas)
        summary_result = {
            "engine": result["engine"],
            "orm_framework": result["orm_framework"],
            "migration_tool": result["migration_tool"],
            "extracted_at": result["extracted_at"],
            "schemas": summary_schemas,
        }
        save_json(os.path.abspath(args.summary_output), summary_result)

    save_json(output_path, result)

    table_count = sum(
        len(s["tables"]) for s in schemas.values()
    )
    print(
        f"Extracted {len(schemas)} schema(s), {table_count} table(s)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
