#!/usr/bin/env python3
"""Deterministic verification of XML code references against the codebase.

For each XML source document, checks every typed ref against the actual
codebase: db refs against SQLAlchemy models, code refs against AST symbols,
flow refs against @flow decorators, env refs against Settings classes and
.env files, config refs against filesystem, enum refs against enum classes.

Usage:
    python3 verify-xml-refs.py \
        --xml-dir PATH \
        --project-root PATH \
        --findings-file PATH \
        [--audience FILTER]

Appends findings to --findings-file atomically. Exit 0 always
(findings are data, not errors).

Architecture follows verify-references.py: file cache, walk refs,
produce findings, exit 0 always.
"""

import argparse
import importlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json
from lib.symbols import (
    extract_class_attributes,
    extract_decorated_functions,
    extract_enum_values,
    extract_function_signatures,
    extract_python_symbols,
    extract_sqlalchemy_models,
)
from lib.xml_doc import parse_xml_doc, walk_sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEP_NAME_RE = re.compile(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)")


def _parse_dep_name(dep_str):
    """Extract normalized package name from a PEP 508 dependency string."""
    m = _DEP_NAME_RE.match(dep_str.strip())
    if m:
        return re.sub(r"[-_.]+", "-", m.group(1)).lower()
    return dep_str.strip().lower()


# ---------------------------------------------------------------------------
# Source cache
# ---------------------------------------------------------------------------

class SourceCache:
    """Lazy-loading cache for Python source analysis results."""

    def __init__(self, project_root, database_model=None):
        self.project_root = project_root
        self.database_model = database_model  # Optional pre-extracted schema data
        self._source = {}       # rel_path -> source text (or None)
        self._symbols = {}      # rel_path -> set of symbol names
        self._signatures = {}   # rel_path -> dict of func_name -> [params]
        self._sqla_models = {}  # rel_path -> dict from extract_sqlalchemy_models
        self._class_attrs = {}  # (rel_path, class_name) -> set
        self._enum_values = {}  # (rel_path, class_name) -> dict
        self._decorators = {}   # (rel_path, decorator) -> list

    def _read_source(self, rel_path):
        if rel_path in self._source:
            return self._source[rel_path]
        abs_path = os.path.join(self.project_root, rel_path)
        if not os.path.isfile(abs_path):
            self._source[rel_path] = None
            return None
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                src = f.read()
        except OSError:
            self._source[rel_path] = None
            return None
        self._source[rel_path] = src
        return src

    def get_symbols(self, rel_path):
        if rel_path not in self._symbols:
            src = self._read_source(rel_path)
            self._symbols[rel_path] = extract_python_symbols(src) if src else set()
        return self._symbols[rel_path]

    def get_signatures(self, rel_path):
        if rel_path not in self._signatures:
            src = self._read_source(rel_path)
            self._signatures[rel_path] = extract_function_signatures(src) if src else {}
        return self._signatures[rel_path]

    def get_sqla_models(self, rel_path):
        if rel_path not in self._sqla_models:
            src = self._read_source(rel_path)
            self._sqla_models[rel_path] = extract_sqlalchemy_models(src) if src else {}
        return self._sqla_models[rel_path]

    def get_class_attrs(self, rel_path, class_name):
        key = (rel_path, class_name)
        if key not in self._class_attrs:
            src = self._read_source(rel_path)
            self._class_attrs[key] = extract_class_attributes(src, class_name) if src else set()
        return self._class_attrs[key]

    def get_enum_values(self, rel_path, class_name):
        key = (rel_path, class_name)
        if key not in self._enum_values:
            src = self._read_source(rel_path)
            self._enum_values[key] = extract_enum_values(src, class_name) if src else {}
        return self._enum_values[key]

    def get_decorated_functions(self, rel_path, decorator):
        key = (rel_path, decorator)
        if key not in self._decorators:
            src = self._read_source(rel_path)
            self._decorators[key] = extract_decorated_functions(src, decorator) if src else []
        return self._decorators[key]

    def file_exists(self, rel_path):
        abs_path = os.path.join(self.project_root, rel_path)
        return os.path.exists(abs_path)

    def walk_py_files(self):
        """Yield relative paths of all .py files in the project."""
        for dirpath, dirnames, filenames in os.walk(self.project_root):
            # Prune skipped directories in-place
            dirnames[:] = [d for d in dirnames if d not in self._SKIP_DIRS]
            for fname in filenames:
                if fname.endswith(".py"):
                    abs_path = os.path.join(dirpath, fname)
                    yield os.path.relpath(abs_path, self.project_root)

    _WALK_EXTENSIONS = {
        ".py", ".yaml", ".yml", ".toml", ".ini", ".service",
        ".env", ".json", ".sh",
    }
    _SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".tox"}

    def walk_project_files(self):
        """Yield relative paths of source/config files for literal grep."""
        for dirpath, dirnames, filenames in os.walk(self.project_root):
            # Prune skipped directories in-place
            dirnames[:] = [d for d in dirnames if d not in self._SKIP_DIRS]
            for fname in filenames:
                _, ext = os.path.splitext(fname)
                if ext in self._WALK_EXTENSIONS or fname.startswith(".env"):
                    abs_path = os.path.join(dirpath, fname)
                    yield os.path.relpath(abs_path, self.project_root)

    def get_pyproject_deps(self):
        """Parse pyproject.toml and return a set of dependency package names."""
        if hasattr(self, "_pyproject_deps"):
            return self._pyproject_deps

        deps = set()
        toml_path = os.path.join(self.project_root, "pyproject.toml")
        if not os.path.isfile(toml_path):
            self._pyproject_deps = deps
            return deps

        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib
            except ModuleNotFoundError:
                self._pyproject_deps = deps
                return deps

        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            self._pyproject_deps = deps
            return deps

        # [project.dependencies]
        for dep_str in data.get("project", {}).get("dependencies", []):
            deps.add(_parse_dep_name(dep_str))

        # [project.optional-dependencies]
        for extras_list in data.get("project", {}).get("optional-dependencies", {}).values():
            for dep_str in extras_list:
                deps.add(_parse_dep_name(dep_str))

        self._pyproject_deps = deps
        return deps


# ---------------------------------------------------------------------------
# Ref checkers
# ---------------------------------------------------------------------------

def check_db_ref(ref, cache):
    """Check a db ref (schema.table.column) against database model or SQLAlchemy AST."""
    schema = ref.get("schema", "")
    table = ref.get("table", "")
    column = ref.get("column")

    # Prefer database model when available (authoritative, pre-extracted)
    if cache.database_model:
        return _check_db_ref_from_model(schema, table, column, cache.database_model)

    # Fallback: scan all Python files for SQLAlchemy models
    return _check_db_ref_from_ast(schema, table, column, cache)


def _extract_column_names(columns):
    """Extract column name set from list-of-dicts or dict-of-dicts format."""
    if isinstance(columns, list):
        return {col["name"] for col in columns if isinstance(col, dict) and "name" in col}
    if isinstance(columns, dict):
        return set(columns.keys())
    return set()


def _check_db_ref_from_model(schema, table, column, db_model):
    """Check db ref against pre-extracted database-model.json data."""
    schemas = db_model.get("schemas", {})
    if schema and schema not in schemas:
        available = ", ".join(sorted(schemas.keys())) if schemas else "(none)"
        return f"Schema `{schema}` not found in database model (available: {available})"

    # If schema specified, check within that schema
    if schema:
        tables = schemas[schema].get("tables", {})
        if table not in tables:
            available = ", ".join(sorted(tables.keys())) if tables else "(none)"
            return f"Table `{table}` not found in schema `{schema}` (available: {available})"
        if column:
            col_names = _extract_column_names(tables[table].get("columns", {}))
            if column not in col_names:
                available = ", ".join(sorted(col_names)) if col_names else "(none)"
                return f"Column `{column}` not found on `{schema}.{table}` (columns: {available})"
        return None

    # No schema specified — search all schemas
    for s_name, s_data in schemas.items():
        tables = s_data.get("tables", {})
        if table in tables:
            if column:
                col_names = _extract_column_names(tables[table].get("columns", {}))
                if column not in col_names:
                    available = ", ".join(sorted(col_names)) if col_names else "(none)"
                    return f"Column `{column}` not found on `{s_name}.{table}` (columns: {available})"
            return None

    return f"Table `{table}` not found in database model"


def _check_db_ref_from_ast(schema, table, column, cache):
    """Check db ref against SQLAlchemy models via AST (fallback)."""
    for py_path in cache.walk_py_files():
        models = cache.get_sqla_models(py_path)
        if table in models:
            model = models[table]
            if schema and model["schema"] and model["schema"] != schema:
                return f"Table `{table}` exists but in schema `{model['schema']}`, not `{schema}`"
            if column and column not in model["columns"]:
                return f"Column `{column}` not found on table `{table}` (columns: {', '.join(model['columns'])})"
            return None

    return f"Table `{table}` not found in any SQLAlchemy model"


def _is_dotted_module(module):
    """Check if a module string looks like a dotted package path (not a local file)."""
    return "." in module and "/" not in module and not module.endswith(".py")


def _check_import(module, name):
    """Try to verify a symbol exists in an installed package.

    Returns:
        True  — symbol found in the imported module
        False — module imported but symbol not found
        None  — module could not be imported (not installed)
    """
    try:
        mod = importlib.import_module(module)
        return hasattr(mod, name)
    except Exception:
        return None


def check_code_ref(ref, cache):
    """Check a code ref (class/function/variable with attrs/params) against AST."""
    kind = ref.get("kind", "")
    name = ref.get("name", "")
    module = ref.get("module", "")

    # If module specified, check that file specifically
    if module:
        symbols = cache.get_symbols(module)
        if name not in symbols:
            # Local file didn't resolve — try as installed package
            if _is_dotted_module(module):
                result = _check_import(module, name)
                if result is True:
                    return None  # Found in installed package
                if result is False:
                    return f"`{name}` not found in `{module}`"
                # result is None — not installed, skip rather than flag
                return None
            return f"`{name}` not found in `{module}`"

        if kind == "class":
            attr = ref.get("attr")
            if attr:
                attrs = cache.get_class_attrs(module, name)
                if attr not in attrs:
                    return f"Attribute `{attr}` not found on class `{name}` in `{module}`"

        if kind == "function":
            param = ref.get("param")
            if param:
                sigs = cache.get_signatures(module)
                params = sigs.get(name)
                if params is not None:
                    if "**" not in params and param not in params:
                        return f"Parameter `{param}` not found on `{name}()` in `{module}` (params: {', '.join(params)})"

        return None  # Found

    # No module specified — scan all Python files
    found_symbol = False
    best_mismatch = None
    for py_path in cache.walk_py_files():
        symbols = cache.get_symbols(py_path)
        if name in symbols:
            found_symbol = True

            if kind == "class":
                attr = ref.get("attr")
                if attr:
                    attrs = cache.get_class_attrs(py_path, name)
                    if attr not in attrs:
                        if best_mismatch is None:
                            best_mismatch = f"Attribute `{attr}` not found on class `{name}` (checked {py_path})"
                        continue  # Maybe another file has it
                return None

            if kind == "function":
                param = ref.get("param")
                if param:
                    sigs = cache.get_signatures(py_path)
                    params = sigs.get(name)
                    if params is not None and "**" not in params and param not in params:
                        if best_mismatch is None:
                            best_mismatch = f"Parameter `{param}` not found on `{name}()` (checked {py_path}, params: {', '.join(params)})"
                        continue  # Maybe another file has it
                return None

            return None

    if found_symbol and best_mismatch:
        return best_mismatch
    return f"`{name}` not found in any Python file"


def check_flow_ref(ref, cache):
    """Check a flow ref against @flow decorated functions."""
    flow_name = ref.get("name", "")

    for py_path in cache.walk_py_files():
        flows = cache.get_decorated_functions(py_path, "flow")
        # Flow names may be the function name or a name= argument
        # We check function names; name= extraction would need deeper AST analysis
        flow_names = set()
        for fn_name in flows:
            flow_names.add(fn_name)
            # Prefect convention: function name with underscores → flow name with hyphens
            flow_names.add(fn_name.replace("_", "-"))
        if flow_name in flow_names:
            return None

    return f"Flow `{flow_name}` not found (no @flow-decorated function matches)"


def check_env_ref(ref, cache):
    """Check an env ref against Settings classes and .env files."""
    env_name = ref.get("name", "")

    # Check .env.example and .env files
    for env_file in [".env.example", ".env", ".env.template"]:
        abs_path = os.path.join(cache.project_root, env_file)
        if os.path.isfile(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        if "=" in stripped:
                            key = stripped.split("=", 1)[0].strip()
                            if key == env_name:
                                return None
            except OSError:
                pass

    # Check Python source for Settings/Config classes with the attribute
    for py_path in cache.walk_py_files():
        symbols = cache.get_symbols(py_path)
        for sym_name in symbols:
            if "settings" in sym_name.lower() or "config" in sym_name.lower():
                attrs = cache.get_class_attrs(py_path, sym_name)
                # Env vars may be uppercase in docs but lowercase attribute
                if env_name in attrs or env_name.lower() in attrs:
                    return None

    # Also check os.environ.get / os.getenv patterns (loose — just grep source)
    for py_path in cache.walk_py_files():
        src = cache._read_source(py_path)
        if src and env_name in src:
            return None

    return f"Environment variable `{env_name}` not found in .env files or source code"


def check_config_ref(ref, cache):
    """Check a config ref against filesystem existence."""
    config_path = ref.get("path", "")
    if cache.file_exists(config_path):
        return None
    return f"Config file `{config_path}` does not exist"


def check_enum_ref(ref, cache):
    """Check an enum ref against enum class values."""
    cls = ref.get("class", "")
    value = ref.get("value", "")

    for py_path in cache.walk_py_files():
        symbols = cache.get_symbols(py_path)
        if cls in symbols:
            members = cache.get_enum_values(py_path, cls)
            if members:
                # Check if value matches any member name or member value
                all_values = set(members.keys()) | set(members.values())
                if value in all_values:
                    return None

            # Also check class attributes for non-enum constant patterns
            attrs = cache.get_class_attrs(py_path, cls)
            if value in attrs or value.upper() in attrs:
                return None

    return f"Enum value `{value}` not found on class `{cls}`"


def check_dep_ref(ref, cache):
    """Check a dep ref against pyproject.toml dependencies."""
    ref_name = ref.get("name", "")
    normalized = re.sub(r"[-_.]+", "-", ref_name).lower()
    deps = cache.get_pyproject_deps()
    if normalized in deps:
        return None
    return f"Dependency `{ref_name}` not found in pyproject.toml"


def check_literal_ref(ref, cache):
    """Check a literal ref by grepping project source/config files."""
    ref_name = ref.get("name", "")
    for rel_path in cache.walk_project_files():
        src = cache._read_source(rel_path)
        if src and ref_name in src:
            return None
    return f"Literal `{ref_name}` not found in any project file"


def check_ext_ref(ref, cache):
    """Check an ext ref — always valid (external tools have no codebase footprint)."""
    return None


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------

CHECKER_BY_TYPE = {
    "db": check_db_ref,
    "code": check_code_ref,
    "flow": check_flow_ref,
    "env": check_env_ref,
    "config": check_config_ref,
    "enum": check_enum_ref,
    "dep": check_dep_ref,
    "literal": check_literal_ref,
    "ext": check_ext_ref,
}


def _make_finding(document, section, audience, description, suggestion, check="xml-ref-integrity"):
    """Create a finding dict matching verify-references.py format."""
    return {
        "document": document,
        "section": section,
        "audience": audience,
        "check": check,
        "description": description,
        "suggestion": suggestion,
        "group_id": f"{document}/{section}",
    }


def _doc_name_from_path(xml_path):
    """Extract document name from XML filename (e.g., OPERATIONS.xml → OPERATIONS)."""
    return os.path.splitext(os.path.basename(xml_path))[0]


def _check_malformed_ref(ref, body):
    """Check a malformed ref against the section body.

    Returns (check_type, description) or None if no finding needed.
    """
    original_type = ref.get("original_type", "?")

    # Extract candidate identifiers from all non-empty string fields
    candidates = []
    for k, v in ref.items():
        if k in ("type", "original_type") or not isinstance(v, str):
            continue
        if v.strip():
            candidates.append(v.strip())

    if not candidates:
        return (
            "malformed-ref-empty",
            f"Malformed {original_type} ref has no identifiable fields",
        )

    for candidate in candidates:
        if candidate in body:
            return (
                "malformed-ref-resolved",
                f"Malformed {original_type} ref has candidate `{candidate}` found in section body",
            )

    cands_str = ", ".join(f"`{c}`" for c in candidates)
    return (
        "malformed-ref-unresolved",
        f"Malformed {original_type} ref with candidates {cands_str} — none found in section body",
    )


def verify_xml_file(xml_path, cache, doc=None):
    """Verify all refs in a single XML document.

    Returns list of finding dicts.
    """
    if doc is None:
        doc = parse_xml_doc(xml_path)
    audience = doc["audience"]
    doc_name = _doc_name_from_path(xml_path)

    findings = []
    for path, section in walk_sections(doc["sections"]):
        body = section.get("body", "")
        for ref in section["refs"]:
            ref_type = ref.get("type", "")

            # Handle malformed refs before normal dispatch
            if ref_type == "malformed":
                result = _check_malformed_ref(ref, body)
                if result:
                    check_type, description = result
                    findings.append(_make_finding(
                        document=doc_name,
                        section=path,
                        audience=audience,
                        description=description,
                        suggestion="Re-generate this section to emit correct typed refs",
                        check=check_type,
                    ))
                continue

            checker = CHECKER_BY_TYPE.get(ref_type)
            if not checker:
                continue

            error = checker(ref, cache)
            if error:
                findings.append(_make_finding(
                    document=doc_name,
                    section=path,
                    audience=audience,
                    description=error,
                    suggestion=_suggestion_for_type(ref_type),
                ))

    return findings


def _suggestion_for_type(ref_type):
    """Return a fix suggestion based on ref type."""
    suggestions = {
        "db": "Update the documentation to match the current database schema",
        "code": "Re-generate this section to pick up current code structure",
        "flow": "Update the flow name to match the current @flow decorator",
        "env": "Update the environment variable name or add it to .env.example",
        "config": "Update the config file path or create the missing file",
        "enum": "Update the enum value to match the current class definition",
        "dep": "Update the dependency name or add it to pyproject.toml",
        "literal": "Update the literal string or verify it exists in the project",
        "ext": "Update the external tool name",
    }
    return suggestions.get(ref_type, "Update documentation to match codebase")


def main():
    parser = argparse.ArgumentParser(
        description="Verify XML code references against the codebase"
    )
    parser.add_argument(
        "--xml-dir", required=True,
        help="Path to xml-sources directory",
    )
    parser.add_argument(
        "--project-root", required=True,
        help="Absolute path to project root",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to findings JSON file to append results to",
    )
    parser.add_argument(
        "--audience",
        help="Audience filter (e.g., 'devops') — only verify matching XML files",
    )
    parser.add_argument(
        "--database-model",
        help="Path to database-model.json for authoritative db ref validation",
    )

    args = parser.parse_args()
    xml_dir = os.path.abspath(args.xml_dir)
    project_root = os.path.abspath(args.project_root)
    findings_file = os.path.abspath(args.findings_file)

    if not os.path.isdir(xml_dir):
        print("No xml-sources directory found, skipping XML ref verification", file=sys.stderr)
        sys.exit(0)

    # Load database model if provided
    database_model = None
    if args.database_model and os.path.isfile(args.database_model):
        database_model = load_json(args.database_model)
        if database_model and database_model.get("extraction") == "skipped":
            database_model = None  # Skip marker — fall back to AST
        if database_model:
            print(f"  Using database model: {args.database_model}", file=sys.stderr)

    cache = SourceCache(project_root, database_model=database_model)

    # Collect XML files
    xml_files = []
    for dirpath, _dirnames, filenames in os.walk(xml_dir):
        for fname in filenames:
            if fname.endswith(".xml"):
                xml_files.append(os.path.join(dirpath, fname))

    if not xml_files:
        print("No XML files found, skipping XML ref verification", file=sys.stderr)
        sys.exit(0)

    # Optional audience filter
    if args.audience:
        filter_audiences = set(args.audience.split(","))
    else:
        filter_audiences = None

    new_findings = []
    total_refs = 0
    for xml_path in sorted(xml_files):
        doc = parse_xml_doc(xml_path)
        if filter_audiences and doc["audience"] not in filter_audiences and doc["audience"] != "all":
            continue

        doc_findings = verify_xml_file(xml_path, cache, doc=doc)
        doc_refs = sum(len(s["refs"]) for _, s in walk_sections(doc["sections"]))
        total_refs += doc_refs
        new_findings.extend(doc_findings)

        doc_name = _doc_name_from_path(xml_path)
        n = len(doc_findings)
        print(f"  {doc_name}: {doc_refs} refs checked, {n} findings", file=sys.stderr)

    # Load existing findings, extend, save atomically
    existing = load_json(findings_file, default=[])
    existing.extend(new_findings)
    save_json(findings_file, existing)

    n = len(new_findings)
    print(f"XML ref integrity: {total_refs} refs checked, {n} findings", file=sys.stderr)


if __name__ == "__main__":
    main()
