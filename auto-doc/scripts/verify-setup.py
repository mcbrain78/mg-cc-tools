#!/usr/bin/env python3
"""Setup and prerequisite checks for the verify pipeline.

Replaces Steps 1-3 of the verify orchestrator: loads config, checks
prerequisites, builds runtime paths, runs prep scripts, and initializes
per-agent findings files.

Usage:
    python3 verify-setup.py \
        --scan-file .mg/docs/docs-scan.json \
        --config .mg/docs/.docs.config.json \
        --global-config {GLOBAL_CONFIG} \
        --checks-file {CHECKS_FILE} \
        --scripts-dir {SCRIPTS_DIR} \
        --templates-dir {TEMPLATES_DIR} \
        --findings-prefix editorial-singledoc

Stdout (JSON): all runtime paths needed by the orchestrator.
Exit 1 with stderr message on prereq failure. Exit 0 on success.

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json


def load_config(config_path, global_config_path):
    """Load project config, falling back to global config.

    Args:
        config_path: Path to project-local .docs.config.json.
        global_config_path: Path to global fallback config.

    Returns:
        Parsed config dict.

    Raises:
        SystemExit: If neither config file exists.
    """
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
    """Extract root_path from the first few lines of scan data.

    Args:
        scan_path: Path to docs-scan.json.

    Returns:
        The root_path string.

    Raises:
        SystemExit: If scan file missing or root_path not found.
    """
    if not os.path.isfile(scan_path):
        print(
            f"Error: No scan data found at {scan_path}.\n"
            "Run /mg:auto-doc-scan first to analyze the project.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read first 2KB to find root_path without loading entire file
    with open(scan_path, "r", encoding="utf-8") as f:
        head = f.read(2048)

    # Try parsing as complete JSON first (small files / tests)
    try:
        obj = json.loads(head)
        if "root_path" in obj:
            return obj["root_path"]
    except json.JSONDecodeError:
        pass

    # For large files, extract from partial JSON via regex-like search
    for line in head.splitlines():
        stripped = line.strip().rstrip(",")
        if '"root_path"' in stripped:
            try:
                obj = json.loads("{" + stripped + "}")
                return obj["root_path"]
            except (json.JSONDecodeError, KeyError):
                pass

    print(
        f"Error: could not extract root_path from {scan_path}",
        file=sys.stderr,
    )
    sys.exit(1)


def build_paths(project_root, docs_dir, checks_file, findings_prefix):
    """Build all runtime paths from inputs.

    Args:
        project_root: Absolute path to the project root.
        docs_dir: Relative docs directory (e.g., 'docs/auto-doc').
        checks_file: Absolute path to verify-checks.json.
        findings_prefix: Prefix name for editorial findings (e.g., 'editorial-singledoc').

    Returns:
        Dict with all path values.
    """
    docs_dir_abs = os.path.join(project_root, docs_dir)
    mg_docs = os.path.join(project_root, ".mg", "docs")
    tmp_dir = os.path.join(mg_docs, "tmp")

    return {
        "project_root": project_root,
        "docs_dir_abs": docs_dir_abs,
        "glossary_path": os.path.join(docs_dir_abs, "GLOSSARY.md"),
        "findings_file": os.path.join(mg_docs, "docs-verify-findings.json"),
        "findings_prefix": os.path.join(mg_docs, f"docs-verify-findings-{findings_prefix}"),
        "checks_file": checks_file,
        "manifest": os.path.join(tmp_dir, "review-chunks", "manifest.json"),
        "scan_context_path": os.path.join(tmp_dir, "verify-scan-context.json"),
        "tmp_dir": tmp_dir,
        "fact_checker_findings": {
            "code_example": os.path.join(mg_docs, "docs-verify-findings-code-example.json"),
            "data_model": os.path.join(mg_docs, "docs-verify-findings-data-model.json"),
            "cross_doc": os.path.join(mg_docs, "docs-verify-findings-cross-doc.json"),
            "completeness": os.path.join(mg_docs, "docs-verify-findings-completeness.json"),
        },
    }


def check_prereqs(scan_path, docs_dir_abs):
    """Validate that prerequisites exist.

    Args:
        scan_path: Path to docs-scan.json.
        docs_dir_abs: Absolute path to docs directory.

    Raises:
        SystemExit: If any prerequisite fails.
    """
    if not os.path.isfile(scan_path):
        print(
            f"Error: No scan data found at {scan_path}.\n"
            "Run /mg:auto-doc-scan first to analyze the project.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not os.path.isdir(docs_dir_abs):
        print(
            f"Error: No generated documentation found in {docs_dir_abs}.\n"
            "Run /mg:auto-doc-generate first to create documentation.",
            file=sys.stderr,
        )
        sys.exit(1)


def run_prep_scripts(paths, scripts_dir, templates_dir, scan_file, audience=None):
    """Run the 4 prep scripts that set up the verify workspace.

    Args:
        paths: Dict from build_paths().
        scripts_dir: Absolute path to scripts directory.
        templates_dir: Absolute path to templates directory.
        scan_file: Absolute path to docs-scan.json.
        audience: Optional comma-separated audience filter string.

    Raises:
        SystemExit: On critical prep script failure.
    """
    project_root = paths["project_root"]
    mg_docs = os.path.join(project_root, ".mg", "docs")

    # Ensure workspace dirs exist
    os.makedirs(os.path.join(mg_docs, "scan-logs"), exist_ok=True)
    os.makedirs(paths["tmp_dir"], exist_ok=True)

    # 1. Clean prior verify artifacts
    _run_script(
        [sys.executable, os.path.join(scripts_dir, "list-verify-findings.py"),
         "--clean", "--findings-file", paths["findings_file"]],
        label="list-verify-findings --clean",
        critical=True,
    )

    # 2. Extract verify context
    _run_script(
        [sys.executable, os.path.join(scripts_dir, "extract-verify-context.py"),
         "--scan-file", scan_file,
         "--output", paths["scan_context_path"],
         "--templates-dir", templates_dir],
        label="extract-verify-context",
        critical=True,
    )

    # 3. Prepare doc review manifest
    prep_cmd = [
        sys.executable, os.path.join(scripts_dir, "prepare-doc-review.py"),
        "--docs-dir", paths["docs_dir_abs"],
        "--output-dir", os.path.join(paths["tmp_dir"], "review-chunks"),
        "--token-limit", "5000",
    ]
    if audience:
        prep_cmd.extend(["--audience", audience])
    _run_script(prep_cmd, label="prepare-doc-review", critical=True)

    # 4. Verify references (non-critical — log and continue)
    _run_script(
        [sys.executable, os.path.join(scripts_dir, "verify-references.py"),
         "--manifests-dir", os.path.join(mg_docs, "reference-manifests"),
         "--project-root", project_root,
         "--scan-file", scan_file,
         "--findings-file", paths["findings_file"]],
        label="verify-references",
        critical=False,
    )

    # 5. Init fact-checker findings files
    for key, fpath in paths["fact_checker_findings"].items():
        _run_script(
            [sys.executable, os.path.join(scripts_dir, "list-verify-findings.py"),
             "--init", "--findings-file", fpath],
            label=f"init {key} findings",
            critical=True,
        )


def _run_script(cmd, label, critical=True):
    """Run a subprocess, handling errors.

    Args:
        cmd: Command list for subprocess.run.
        label: Human-readable label for error messages.
        critical: If True, exit on failure. If False, log and continue.
    """
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
        description="Setup and prerequisite checks for verify pipeline"
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
        "--checks-file", required=True,
        help="Path to verify-checks.json",
    )
    parser.add_argument(
        "--scripts-dir", required=True,
        help="Path to scripts directory",
    )
    parser.add_argument(
        "--templates-dir", required=True,
        help="Path to templates directory",
    )
    parser.add_argument(
        "--findings-prefix", default="editorial-singledoc",
        help="Prefix for editorial findings files (default: editorial-singledoc)",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Comma-separated audience filter (e.g., 'devops,end-users'). Passed to prepare-doc-review.",
    )

    args = parser.parse_args()

    scan_file = os.path.abspath(args.scan_file)
    config_path = os.path.abspath(args.config)
    global_config_path = os.path.abspath(args.global_config)
    checks_file = os.path.abspath(args.checks_file)
    scripts_dir = os.path.abspath(args.scripts_dir)
    templates_dir = os.path.abspath(args.templates_dir)

    # Load config
    config = load_config(config_path, global_config_path)
    docs_dir = config.get("docs_dir", "docs/auto-doc")

    # Read project root from scan data
    project_root = read_project_root(scan_file)

    # Check prerequisites
    docs_dir_abs = os.path.join(project_root, docs_dir)
    check_prereqs(scan_file, docs_dir_abs)

    # Build paths
    paths = build_paths(project_root, docs_dir, checks_file, args.findings_prefix)

    # Run prep scripts
    run_prep_scripts(paths, scripts_dir, templates_dir, scan_file, audience=args.audience)

    # Output all paths as JSON
    print(json.dumps(paths, indent=2))


if __name__ == "__main__":
    main()
