#!/usr/bin/env python3
"""Setup and workspace preparation for the generate pipeline.

Replaces Steps 1-3 of the generate orchestrator: loads config, detects
mode, builds runtime paths, creates directories, cleans stale artifacts,
splits scan data into per-audience views, and loads standing notes.

Usage:
    python3 generate-setup.py \
        --scan-file .mg/docs/docs-scan.json \
        --config .mg/docs/.docs.config.json \
        --global-config {MG_INSTALL_GLOBAL_CONFIG} \
        --scripts-dir {MG_INSTALL_SCRIPTS_DIR} \
        [--audience end-users,devops]

Stdout (JSON): all runtime paths, mode, audience config, and grouped
notes needed by the orchestrator.
Exit 1 with stderr message on failure. Exit 0 on success.

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import glob as glob_mod
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def load_config(config_path, global_config_path):
    """Load config by merging global defaults with project overrides.

    Global config provides defaults (audiences, docs_dir, etc.).
    Project config overrides specific keys. This ensures a project
    config with only user_interfaces still gets audiences from global.
    """
    global_config = load_json(global_config_path)
    project_config = load_json(config_path)

    if global_config is None and project_config is None:
        print(
            f"Error: no config found at {config_path} or {global_config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    base = global_config or {}
    overlay = project_config or {}
    merged = {**base, **overlay}
    return merged


def read_project_root(scan_path):
    """Extract root_path from the first few lines of scan data."""
    if not os.path.isfile(scan_path):
        print(
            f"Error: No scan data found at {scan_path}.\n"
            "Run /mg:auto-doc-scan first to analyze the project.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(scan_path, "r", encoding="utf-8") as f:
        head = f.read(2048)

    try:
        obj = json.loads(head)
        if "root_path" in obj:
            return obj["root_path"]
    except json.JSONDecodeError:
        pass

    for line in head.splitlines():
        stripped = line.strip().rstrip(",")
        if '"root_path"' in stripped:
            try:
                obj = json.loads("{" + stripped + "}")
                return obj["root_path"]
            except (json.JSONDecodeError, KeyError):
                pass

    print(f"Error: could not extract root_path from {scan_path}", file=sys.stderr)
    sys.exit(1)


def _read_scan_date(scan_path):
    """Extract scan_date from the scan file.

    Returns the scan_date string, or empty string if not found.
    """
    if not os.path.isfile(scan_path):
        return ""
    try:
        with open(scan_path, "r", encoding="utf-8") as f:
            head = f.read(2048)
        obj = json.loads(head)
        return obj.get("scan_date", "")
    except (json.JSONDecodeError, OSError):
        return ""


def detect_mode(docs_dir_abs):
    """Detect initial vs update mode from existing docs."""
    md_files = glob_mod.glob(os.path.join(docs_dir_abs, "**", "*.md"), recursive=True)
    return "update" if md_files else "initial"


def get_enabled_audiences(config, audience_filter=None):
    """Return dict of enabled audiences, optionally filtered.

    Args:
        config: Parsed config dict with 'audiences' key.
        audience_filter: Optional set of audience names to restrict to.

    Returns:
        Dict of audience_name -> {documents: [...]} for enabled audiences.
    """
    audiences_config = config.get("audiences", {})
    result = {}
    for name, aud_conf in audiences_config.items():
        if not aud_conf.get("enabled", True):
            continue
        if audience_filter and name not in audience_filter:
            continue
        result[name] = {
            "documents": aud_conf.get("documents", []),
        }
    return result


def build_paths(project_root, docs_dir):
    """Build all runtime paths from inputs."""
    docs_dir_abs = os.path.join(project_root, docs_dir)
    mg_docs = os.path.join(project_root, ".mg", "docs")
    tmp_dir = os.path.join(mg_docs, "tmp")

    return {
        "project_root": project_root,
        "docs_dir_abs": docs_dir_abs,
        "scan_data_path": os.path.join(mg_docs, "docs-scan.json"),
        "tmp_dir": tmp_dir,
        "project_model_path": os.path.join(tmp_dir, "project-model.json"),
        "database_model_path": os.path.join(tmp_dir, "database-model.json"),
        "notes_file": os.path.join(tmp_dir, "all-notes.json"),
        "notes_inbox": os.path.join(mg_docs, "notes-inbox.json"),
        "manifests_dir": os.path.join(mg_docs, "reference-manifests"),
        "scan_logs_dir": os.path.join(mg_docs, "scan-logs"),
    }


def prepare_workspace(paths, mode, audiences, scripts_dir):
    """Create dirs, clean artifacts, split scans, load notes.

    Args:
        paths: Dict from build_paths().
        mode: 'initial' or 'update'.
        audiences: Dict from get_enabled_audiences().
        scripts_dir: Absolute path to scripts directory.

    Returns:
        Dict with scan_views and notes_by_audience.
    """
    docs_dir_abs = paths["docs_dir_abs"]
    tmp_dir = paths["tmp_dir"]
    scan_logs_dir = paths["scan_logs_dir"]
    manifests_dir = paths["manifests_dir"]

    # Create output directories
    for aud in ["end-users", "developers", "agents", "devops"]:
        os.makedirs(os.path.join(docs_dir_abs, aud), exist_ok=True)
    os.makedirs(scan_logs_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(manifests_dir, exist_ok=True)

    # Clean stale term proposals
    for f in glob_mod.glob(os.path.join(scan_logs_dir, "terms-*.json")):
        os.remove(f)

    # Clean glossary reconciliation log
    reconciliation_log = os.path.join(scan_logs_dir, "glossary-reconciliation.log")
    if os.path.exists(reconciliation_log):
        os.remove(reconciliation_log)

    # In initial mode, clear existing manifests
    if mode == "initial":
        for f in glob_mod.glob(os.path.join(manifests_dir, "*.json")):
            os.remove(f)

    # Clean temp files from prior runs
    for pattern in [
        "manifest-*.json", "manifest-entry-*.json",
        "write-state-*.json", "section-*.md",
        "refs-*.json", "header-*.md",
        "heading-state-*.json",
    ]:
        for f in glob_mod.glob(os.path.join(tmp_dir, pattern)):
            os.remove(f)

    # Clean per-run artifacts so they are regenerated fresh
    for stale in [
        "project-model.json",
        "database-model.json",
        "database-model-summary.json",
        "db-table-map.json",
    ]:
        p = os.path.join(tmp_dir, stale)
        if os.path.exists(p):
            os.remove(p)

    # Write last_generated timestamp
    _run_script(
        [sys.executable, os.path.join(scripts_dir, "set-last-generated.py"),
         "--scan-file", paths["scan_data_path"]],
        label="set-last-generated",
    )

    # Split scan data into per-audience views
    scan_views = {}
    for aud_name, aud_conf in audiences.items():
        documents = ",".join(aud_conf["documents"])
        view_path = os.path.join(tmp_dir, f"scan-view-{aud_name}.json")
        _run_script(
            [sys.executable, os.path.join(scripts_dir, "split-scan-by-audience.py"),
             "--input", paths["scan_data_path"],
             "--output", view_path,
             "--mode", "audience",
             "--audience", aud_name,
             "--documents", documents,
             "--project-model-output", paths["project_model_path"]],
            label=f"split-scan {aud_name}",
        )
        scan_views[aud_name] = view_path

    # Glossary view (always created regardless of filter)
    glossary_view = os.path.join(tmp_dir, "scan-view-glossary.json")
    _run_script(
        [sys.executable, os.path.join(scripts_dir, "split-scan-by-audience.py"),
         "--input", paths["scan_data_path"],
         "--output", glossary_view,
         "--mode", "glossary"],
        label="split-scan glossary",
    )
    scan_views["glossary"] = glossary_view

    # Load and group standing notes by audience
    notes_by_audience = _load_notes(paths, scripts_dir, audiences)

    return scan_views, notes_by_audience


def _load_notes(paths, scripts_dir, audiences):
    """Load notes from inbox and group by audience.

    Returns:
        Dict of audience_name -> list of note dicts. Empty dict if no inbox.
    """
    inbox = paths["notes_inbox"]
    notes_file = paths["notes_file"]

    if not os.path.isfile(inbox):
        return {aud: [] for aud in audiences}

    _run_script(
        [sys.executable, os.path.join(scripts_dir, "list-notes.py"),
         "--inbox", inbox,
         "--output", notes_file],
        label="list-notes",
        critical=False,
    )

    notes = load_json(notes_file)
    if not notes:
        return {aud: [] for aud in audiences}

    grouped = {aud: [] for aud in audiences}
    for note in notes:
        classification = note.get("classification")
        if not classification:
            continue
        aud = classification.get("audience")
        if aud in grouped:
            grouped[aud].append(note)

    return grouped


def _extract_database_model(paths, scripts_dir):
    """Run deterministic DB extraction if project uses SQLAlchemy.

    Returns dict with ``full`` and ``summary`` paths if extraction
    succeeded and produced schemas, or None otherwise.
    """
    pm_path = paths["project_model_path"]
    if not os.path.isfile(pm_path):
        return None
    pm = load_json(pm_path)
    if not pm:
        return None
    db = pm.get("database")
    if not db or "sqlalchemy" not in str(
        db.get("orm", db.get("orm_framework", ""))
    ).lower():
        return None

    # Derive search paths from components
    search_dirs = set()
    for comp in pm.get("components", []):
        comp_path = comp.get("path", "")
        if comp_path:
            parent = os.path.dirname(comp_path.rstrip("/"))
            if parent:
                search_dirs.add(parent)
    if not search_dirs:
        return None

    output = paths["database_model_path"]
    summary_output = os.path.join(paths["tmp_dir"], "database-model-summary.json")
    cmd = [
        "uv", "run", "--directory", paths["project_root"],
        sys.executable, os.path.join(scripts_dir, "extract-database-model.py"),
        "--project-root", paths["project_root"],
        "--search-paths", ",".join(sorted(search_dirs)),
        "--project-model", pm_path,
        "--output", output,
        "--summary-output", summary_output,
    ]
    _run_script(cmd, "extract-database-model", critical=False)

    if os.path.isfile(output):
        result = load_json(output, default={})
        if result.get("schemas"):
            return {"full": output, "summary": summary_output}
    return None


def _has_headings(template_path):
    """Check if a refined template has at least one ## heading.

    Reads the first 2000 bytes and looks for a line starting with '## '.
    Returns False if no heading found (empty/malformed template).
    """
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            head = f.read(2000)
    except OSError:
        return False

    for line in head.splitlines():
        if line.startswith("## "):
            return True
    return False


def _check_stale(template_path, current_scan_date):
    """Check if a refined template is stale relative to scan date.

    Reads first 500 bytes for the REFINED metadata comment.
    Compares scan date in REFINED comment against current_scan_date.
    Both dates are normalized to YYYY-MM-DD (first 10 chars) before comparison.

    Returns True if stale, unreadable, or missing REFINED comment.
    """
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            head = f.read(500)
    except OSError:
        return True  # Can't read = treat as stale

    m = re.search(r"<!--\s*REFINED:.*?scan:\s*(\S+)", head)
    if not m:
        return True  # No REFINED comment = treat as stale

    refined_scan_date = m.group(1).rstrip(",").rstrip("-->").strip()[:10]
    current_date = current_scan_date[:10] if current_scan_date else ""

    return current_date > refined_scan_date


def detect_refined_templates(project_root, audiences, scan_date):
    """Detect refined templates for each audience/document pair.

    Args:
        project_root: Absolute path to project root.
        audiences: Dict from get_enabled_audiences().
        scan_date: scan_date string from docs-scan.json.

    Returns:
        Tuple of (refined_templates dict, stale_templates list).
        refined_templates: {audience: {document: {"path": str, "stale": bool} | None}}
        stale_templates: list of "audience/document" strings for stale entries.
    """
    templates_base = os.path.join(project_root, ".mg", "docs", "templates")
    refined = {}
    stale = []

    for aud_name, aud_conf in audiences.items():
        refined[aud_name] = {}
        for doc in aud_conf.get("documents", []):
            path = os.path.join(templates_base, aud_name, f"{doc}.template.md")
            if os.path.isfile(path) and _has_headings(path):
                is_stale = _check_stale(path, scan_date)
                refined[aud_name][doc] = {"path": path, "stale": is_stale}
                if is_stale:
                    stale.append(f"{aud_name}/{doc}")
            else:
                refined[aud_name][doc] = None

    return refined, stale


def _build_db_table_map(project_model_path, scan_path, tmp_dir):
    """Build section-to-tables mapping from project model and scan data.

    Reads ``database_tables`` from each component in the slimmed project
    model and cross-references with ``source_material_index`` sections
    to produce a map of section_key -> [table_names].

    Returns path to db-table-map.json, or None if no database tables found.
    """
    pm = load_json(project_model_path)
    if not pm:
        return None

    # Build reverse index: component directory -> [table_names]
    dir_to_tables = {}
    for comp in pm.get("components", []):
        tables = comp.get("database_tables", [])
        if not tables:
            continue
        comp_path = comp.get("path", "")
        if comp_path:
            dir_to_tables[comp_path] = tables

    if not dir_to_tables:
        return None

    # Load scan data for source_material_index
    scan_data = load_json(scan_path, default={})
    smi = scan_data.get("source_material_index", {})

    # For each section, collect tables from its source files
    table_map = {}
    for section_key, section_data in smi.items():
        source_files = section_data.get("source_files", [])
        section_tables = set()
        for sf in source_files:
            for comp_path, tables in dir_to_tables.items():
                # Check if source file is within the component's path
                if sf.startswith(comp_path) or sf == comp_path:
                    section_tables.update(tables)
        if section_tables:
            table_map[section_key] = sorted(section_tables)

    if not table_map:
        return None

    output_path = os.path.join(tmp_dir, "db-table-map.json")
    save_json(output_path, table_map)
    return output_path


def _run_script(cmd, label, critical=True):
    """Run a subprocess, handling errors."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        msg = f"Script '{label}' failed (rc={result.returncode})"
        if result.stderr:
            msg += f": {result.stderr.strip()}"
        if critical:
            print(msg, file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Warning: {msg}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Setup and workspace preparation for generate pipeline"
    )
    parser.add_argument(
        "--scan-file", required=True,
        help="Path to docs-scan.json",
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to project .docs.config.json",
    )
    parser.add_argument(
        "--global-config", required=True,
        help="Path to global fallback .docs.config.json",
    )
    parser.add_argument(
        "--scripts-dir", required=True,
        help="Path to scripts directory",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Comma-separated audience filter (e.g., 'end-users,devops')",
    )

    args = parser.parse_args()

    scan_file = os.path.abspath(args.scan_file)
    config_path = os.path.abspath(args.config)
    global_config_path = os.path.abspath(args.global_config)
    scripts_dir = os.path.abspath(args.scripts_dir)
    audience_filter = set(re.split(r"[,\s]+", args.audience.strip())) - {""} if args.audience else None

    # Load config
    config = load_config(config_path, global_config_path)
    docs_dir = config.get("docs_dir", "docs/auto-doc")

    # Read project root from scan data
    project_root = read_project_root(scan_file)

    # Build paths
    paths = build_paths(project_root, docs_dir)

    # Detect mode
    mode = detect_mode(paths["docs_dir_abs"])

    # Get enabled audiences (with optional filter)
    audiences = get_enabled_audiences(config, audience_filter)

    if not audiences:
        print("Error: no matching audiences found", file=sys.stderr)
        sys.exit(1)

    # Read scan_date from scan file for stale template detection
    scan_date = _read_scan_date(scan_file)

    # Detect refined templates
    refined_templates, stale_templates = detect_refined_templates(
        project_root, audiences, scan_date,
    )

    # Prepare workspace
    scan_views, notes_by_audience = prepare_workspace(
        paths, mode, audiences, scripts_dir,
    )

    # Run deterministic database model extraction
    db_result = _extract_database_model(paths, scripts_dir)

    # Build section-to-tables mapping (only if DB extraction succeeded)
    db_table_map_path = None
    if db_result:
        db_table_map_path = _build_db_table_map(
            paths["project_model_path"], scan_file, paths["tmp_dir"],
        )

    # Output everything the orchestrator needs
    result = {
        **paths,
        "database_model_path": db_result["full"] if db_result else None,
        "database_model_summary_path": db_result["summary"] if db_result else None,
        "db_table_map_path": db_table_map_path,
        "mode": mode,
        "audiences": audiences,
        "audience_filter_active": audience_filter is not None,
        "scan_views": scan_views,
        "notes_by_audience": notes_by_audience,
        "refined_templates": refined_templates,
        "stale_templates": stale_templates,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
