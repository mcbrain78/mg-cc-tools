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
import ast
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

    Returns a tuple of:
        - list of unique MetaData objects with populated tables
        - dict mapping model class name -> {table_name, schema, source_file}
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
            return [], {}

    metadata_map = {}  # id(MetaData) -> MetaData
    model_class_map = {}  # class_name -> {table_name, schema, source_file}

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

            # Track model class -> table mapping
            if hasattr(obj, "__tablename__") and hasattr(obj, "__table__"):
                tbl = obj.__table__
                model_class_map[attr_name] = {
                    "table_name": tbl.name,
                    "schema": tbl.schema or "public",
                    "source_file": rel.replace(os.sep, "/"),
                }

    return list(metadata_map.values()), model_class_map


def _build_usage_index(project_root, model_class_map):
    """Build file-level usage index via static AST analysis.

    Walks all .py files under project_root, finds imports of known model
    classes, and tracks which functions reference them.

    Args:
        project_root: Absolute path to the project root.
        model_class_map: Dict from _discover_bases(): class_name -> {table_name, ...}

    Returns:
        Dict with table_definitions and file_usage keys.
    """
    if not model_class_map:
        return {"table_definitions": {}, "file_usage": {}}

    # Build table_definitions from model_class_map
    table_definitions = {}
    for class_name, info in model_class_map.items():
        table_definitions[info["table_name"]] = {
            "schema": info["schema"],
            "model_class": class_name,
            "source_file": info["source_file"],
        }

    known_classes = set(model_class_map.keys())
    # Reverse: class_name -> table_name
    class_to_table = {cn: info["table_name"] for cn, info in model_class_map.items()}

    file_usage = {}

    for dirpath, _dirnames, filenames in os.walk(project_root):
        # Skip hidden dirs, __pycache__, .venv, node_modules
        rel_dir = os.path.relpath(dirpath, project_root)
        if any(
            part.startswith(".") or part == "__pycache__" or part == "node_modules"
            for part in rel_dir.split(os.sep)
        ):
            continue

        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, project_root).replace(os.sep, "/")

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=rel)
            except (SyntaxError, UnicodeDecodeError, OSError):
                print(f"Warning: could not parse {rel}", file=sys.stderr)
                continue

            # Step 1: find imports of known model classes, track aliases
            # alias_to_class: local_name -> class_name
            alias_to_class = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            continue  # skip star imports
                        if alias.name in known_classes:
                            local = alias.asname if alias.asname else alias.name
                            alias_to_class[local] = alias.name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in known_classes:
                            local = alias.asname if alias.asname else alias.name
                            alias_to_class[local] = alias.name

            if not alias_to_class:
                continue

            local_names = set(alias_to_class.keys())

            # Step 2: walk top-level statements for function/class defs
            # and module-level references
            func_tables = {}  # function_name -> set of table_names

            def _collect_names(body_nodes):
                """Collect model class references from AST nodes."""
                tables = set()
                for node in ast.walk(ast.Module(body=body_nodes, type_ignores=[])):
                    if isinstance(node, ast.Name) and node.id in local_names:
                        tables.add(class_to_table[alias_to_class[node.id]])
                    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                        if node.value.id in local_names:
                            tables.add(class_to_table[alias_to_class[node.value.id]])
                return tables

            module_level_tables = set()
            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    tables = _collect_names(stmt.body)
                    if tables:
                        func_tables[stmt.name] = sorted(tables)
                elif isinstance(stmt, ast.ClassDef):
                    # Check class-level and method-level references
                    for item in stmt.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            tables = _collect_names(item.body)
                            if tables:
                                func_tables[f"{stmt.name}.{item.name}"] = sorted(tables)
                        else:
                            module_level_tables.update(_collect_names([item]))
                else:
                    # Module-level statements (assignments, expressions, etc.)
                    # Skip import statements themselves
                    if not isinstance(stmt, (ast.Import, ast.ImportFrom)):
                        module_level_tables.update(_collect_names([stmt]))

            if module_level_tables:
                func_tables["<module>"] = sorted(module_level_tables)

            if func_tables:
                file_usage[rel] = func_tables

    return {"table_definitions": table_definitions, "file_usage": file_usage}


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
    parser.add_argument(
        "--usage-output",
        help="Optional path to write db-usage-index.json (file-level usage index)",
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
    metadata_list, model_class_map = _discover_bases(project_root, python_files)
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

    # Write usage index if requested
    if args.usage_output:
        usage_index = _build_usage_index(project_root, model_class_map)
        save_json(os.path.abspath(args.usage_output), usage_index)

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
