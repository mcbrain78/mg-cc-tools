#!/usr/bin/env python3
"""Setup and workspace preparation for the generate pipeline.

Replaces Steps 1-3 of the generate orchestrator: loads config, detects
mode, builds runtime paths, creates directories, cleans stale artifacts,
splits scan data into per-audience views, and loads standing notes.

Usage:
    python3 generate-setup.py \
        --scan-file .mg/docs/docs-scan.json \
        --config .mg/docs/.docs.config.json \
        --global-config {GLOBAL_CONFIG} \
        --scripts-dir {SCRIPTS_DIR} \
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
from lib.json_io import load_json


def load_config(config_path, global_config_path):
    """Load project config, falling back to global config."""
    config = load_json(config_path)
    if config is not None:
        return config

    config = load_json(global_config_path)
    if config is not None:
        return config

    print(
        f"Error: no config found at {config_path} or {global_config_path}",
        file=sys.stderr,
    )
    sys.exit(1)


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
    ]:
        for f in glob_mod.glob(os.path.join(tmp_dir, pattern)):
            os.remove(f)

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

    # Prepare workspace
    scan_views, notes_by_audience = prepare_workspace(
        paths, mode, audiences, scripts_dir,
    )

    # Output everything the orchestrator needs
    result = {
        **paths,
        "mode": mode,
        "audiences": audiences,
        "audience_filter_active": audience_filter is not None,
        "scan_views": scan_views,
        "notes_by_audience": notes_by_audience,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
