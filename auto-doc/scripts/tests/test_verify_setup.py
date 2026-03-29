"""Tests for verify-setup.py -- verify pipeline setup and prereq checks.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "verify-setup.py",
)

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
)


def _run(args, check=True):
    """Run verify-setup.py with args, return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Script failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout, result.stderr, result.returncode


def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _make_scan_file(tmp, root_path):
    """Create a minimal docs-scan.json with root_path."""
    scan_path = os.path.join(tmp, "docs-scan.json")
    # Mimic real scan data structure — root_path in first few lines
    _write_json(scan_path, {
        "root_path": root_path,
        "source_material_index": {},
        "gap_analysis": {},
    })
    return scan_path


def _make_config(tmp, docs_dir="docs/auto-doc"):
    """Create a minimal config file."""
    config_path = os.path.join(tmp, ".docs.config.json")
    _write_json(config_path, {"docs_dir": docs_dir})
    return config_path


def _make_project(tmp):
    """Create a minimal project structure for full-run tests.

    Returns (project_root, scan_path, config_path).
    """
    project_root = os.path.join(tmp, "project")
    docs_dir = os.path.join(project_root, "docs", "auto-doc")
    mg_docs = os.path.join(project_root, ".mg", "docs")

    os.makedirs(docs_dir)
    os.makedirs(mg_docs)

    # Create a minimal doc file so prepare-doc-review has something to process
    with open(os.path.join(docs_dir, "TEST.md"), "w") as f:
        f.write("# Test\n\nSome content.\n")

    scan_path = os.path.join(mg_docs, "docs-scan.json")
    _write_json(scan_path, {
        "root_path": project_root,
        "source_material_index": {},
        "gap_analysis": {},
    })

    config_path = os.path.join(mg_docs, ".docs.config.json")
    _write_json(config_path, {"docs_dir": "docs/auto-doc"})

    return project_root, scan_path, config_path


# =============================================================================
# load_config tests (via script behavior)
# =============================================================================

class TestLoadConfig:
    """Config loading — project config, fallback to global, missing both fails."""

    def test_uses_project_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            global_config = os.path.join(tmp, "global.json")
            _write_json(global_config, {"docs_dir": "docs/global-docs"})

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", global_config,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            # Should use project config's docs_dir, not global
            assert result["docs_dir_abs"].endswith("docs/auto-doc")

    def test_falls_back_to_global_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, _ = _make_project(tmp)
            nonexistent_config = os.path.join(tmp, "nonexistent.json")
            global_config = os.path.join(tmp, "global.json")
            _write_json(global_config, {"docs_dir": "docs/auto-doc"})

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", nonexistent_config,
                "--global-config", global_config,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            assert result["docs_dir_abs"].endswith("docs/auto-doc")

    def test_missing_both_configs_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, _ = _make_project(tmp)

            _, stderr, rc = _run([
                "--scan-file", scan_path,
                "--config", os.path.join(tmp, "nope1.json"),
                "--global-config", os.path.join(tmp, "nope2.json"),
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ], check=False)

            assert rc != 0
            assert "no config found" in stderr.lower()


# =============================================================================
# read_project_root tests
# =============================================================================

class TestReadProjectRoot:
    """Extracting root_path from scan data."""

    def test_extracts_root_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            assert result["project_root"] == project_root


# =============================================================================
# build_paths tests
# =============================================================================

class TestBuildPaths:
    """Correct path construction from inputs."""

    def test_all_expected_keys_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            expected_keys = {
                "project_root", "docs_dir_abs", "glossary_path",
                "findings_file", "findings_prefix", "checks_file",
                "manifest", "scan_context_path", "tmp_dir",
                "fact_checker_findings",
            }
            assert expected_keys == set(result.keys())

    def test_fact_checker_findings_has_4_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            fc = result["fact_checker_findings"]
            assert set(fc.keys()) == {"code_example", "data_model", "cross_doc", "completeness"}

    def test_findings_prefix_includes_custom_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
                "--findings-prefix", "my-custom",
            ])

            result = json.loads(stdout)
            assert "docs-verify-findings-my-custom" in result["findings_prefix"]


# =============================================================================
# Prerequisite checks
# =============================================================================

class TestPrereqChecks:
    """Missing scan file or docs dir → exit 1 with message."""

    def test_missing_scan_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _make_config(tmp)

            _, stderr, rc = _run([
                "--scan-file", os.path.join(tmp, "nonexistent-scan.json"),
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ], check=False)

            assert rc != 0
            assert "scan" in stderr.lower()

    def test_missing_docs_dir_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create scan file pointing to project root without docs dir
            project_root = os.path.join(tmp, "project")
            os.makedirs(os.path.join(project_root, ".mg", "docs"))
            scan_path = _make_scan_file(
                os.path.join(project_root, ".mg", "docs"),
                project_root,
            )
            config_path = _make_config(tmp)

            _, stderr, rc = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ], check=False)

            assert rc != 0
            assert "documentation" in stderr.lower() or "docs" in stderr.lower()


# =============================================================================
# Full run integration
# =============================================================================

class TestFullRun:
    """Create minimal fixtures, run script, verify JSON output."""

    def test_full_run_produces_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            stdout, stderr, rc = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            assert result["project_root"] == project_root
            assert os.path.isfile(result["manifest"])
            assert os.path.isfile(result["scan_context_path"])

    def test_full_run_creates_workspace_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            assert os.path.isdir(os.path.join(project_root, ".mg", "docs", "scan-logs"))
            assert os.path.isdir(os.path.join(project_root, ".mg", "docs", "tmp"))

    def test_full_run_inits_fact_checker_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--checks-file", os.path.join(tmp, "checks.json"),
                "--scripts-dir", SCRIPTS_DIR,
                "--templates-dir", os.path.join(tmp, "templates"),
            ])

            result = json.loads(stdout)
            for key, fpath in result["fact_checker_findings"].items():
                assert os.path.isfile(fpath), f"Missing {key} findings: {fpath}"
                data = _read_json(fpath)
                assert data == [], f"Expected empty array for {key}"
