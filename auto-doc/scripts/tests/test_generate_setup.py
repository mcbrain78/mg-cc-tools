"""Tests for generate-setup.py -- generate pipeline setup.

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
    "generate-setup.py",
)

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
)


def _run(args, check=True):
    """Run generate-setup.py with args, return (stdout, stderr, returncode)."""
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


def _sample_config():
    return {
        "docs_dir": "docs/auto-doc",
        "audiences": {
            "end-users": {"enabled": True, "documents": ["USER_GUIDE"]},
            "developers": {"enabled": True, "documents": ["ARCHITECTURE"]},
            "devops": {"enabled": True, "documents": ["OPERATIONS"]},
            "agents": {"enabled": True, "documents": ["SYSTEM_MAP"]},
        },
        "shared_documents": ["OVERVIEW", "GLOSSARY"],
    }


def _sample_scan(project_root):
    return {
        "root_path": project_root,
        "source_material_index": {
            "USER_GUIDE/getting-started": {
                "heading": "Getting Started",
                "source_files": [],
            },
            "ARCHITECTURE/system-overview": {
                "heading": "System Overview",
                "source_files": [],
            },
        },
        "gap_analysis": {
            "missing_for_audience": {},
        },
        "gsd_context": {},
    }


def _make_project(tmp, with_docs=False):
    """Create minimal project structure.

    Args:
        tmp: Temp directory.
        with_docs: If True, create a doc file so mode='update'.

    Returns (project_root, scan_path, config_path).
    """
    project_root = os.path.join(tmp, "project")
    docs_dir = os.path.join(project_root, "docs", "auto-doc")
    mg_docs = os.path.join(project_root, ".mg", "docs")

    os.makedirs(docs_dir)
    os.makedirs(mg_docs)

    if with_docs:
        os.makedirs(os.path.join(docs_dir, "end-users"), exist_ok=True)
        with open(os.path.join(docs_dir, "end-users", "USER_GUIDE.md"), "w") as f:
            f.write("# User Guide\n\nContent.\n")

    scan_path = os.path.join(mg_docs, "docs-scan.json")
    _write_json(scan_path, _sample_scan(project_root))

    config_path = os.path.join(mg_docs, ".docs.config.json")
    _write_json(config_path, _sample_config())

    return project_root, scan_path, config_path


def _run_setup(tmp, audience=None, with_docs=False):
    """Helper: create project and run setup."""
    project_root, scan_path, config_path = _make_project(tmp, with_docs=with_docs)

    cmd = [
        "--scan-file", scan_path,
        "--config", config_path,
        "--global-config", config_path,
        "--scripts-dir", SCRIPTS_DIR,
    ]
    if audience:
        cmd.extend(["--audience", audience])

    stdout, _, _ = _run(cmd)
    return project_root, json.loads(stdout)


# =============================================================================
# Core output
# =============================================================================

class TestOutput:
    """Script produces valid JSON with expected keys."""

    def test_produces_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert isinstance(result, dict)

    def test_has_all_path_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            expected = {
                "project_root", "docs_dir_abs", "scan_data_path",
                "tmp_dir", "project_model_path", "notes_file",
                "notes_inbox", "manifests_dir", "scan_logs_dir",
                "mode", "audiences", "audience_filter_active",
                "scan_views", "notes_by_audience",
            }
            assert expected == set(result.keys())

    def test_project_root_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, result = _run_setup(tmp)
            assert result["project_root"] == project_root


# =============================================================================
# Mode detection
# =============================================================================

class TestModeDetection:
    """Detects initial vs update from filesystem."""

    def test_initial_mode_no_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp, with_docs=False)
            assert result["mode"] == "initial"

    def test_update_mode_with_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp, with_docs=True)
            assert result["mode"] == "update"


# =============================================================================
# Audience handling
# =============================================================================

class TestAudiences:
    """Audience config and filtering."""

    def test_all_audiences_without_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert set(result["audiences"].keys()) == {
                "end-users", "developers", "devops", "agents",
            }
            assert result["audience_filter_active"] is False

    def test_filter_single_audience(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp, audience="devops")
            assert set(result["audiences"].keys()) == {"devops"}
            assert result["audience_filter_active"] is True

    def test_filter_multiple_audiences(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp, audience="end-users,devops")
            assert set(result["audiences"].keys()) == {"end-users", "devops"}

    def test_audiences_have_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert result["audiences"]["end-users"]["documents"] == ["USER_GUIDE"]
            assert result["audiences"]["developers"]["documents"] == ["ARCHITECTURE"]

    def test_filter_nonexistent_audience_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            _, stderr, rc = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--scripts-dir", SCRIPTS_DIR,
                "--audience", "nonexistent",
            ], check=False)
            assert rc != 0
            assert "no matching audiences" in stderr.lower()


# =============================================================================
# Scan views
# =============================================================================

class TestScanViews:
    """Per-audience scan view files are created."""

    def test_creates_audience_scan_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            for aud in result["audiences"]:
                view = result["scan_views"][aud]
                assert os.path.isfile(view), f"Missing scan view for {aud}"

    def test_creates_glossary_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert "glossary" in result["scan_views"]
            assert os.path.isfile(result["scan_views"]["glossary"])

    def test_filtered_creates_only_filtered_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp, audience="devops")
            # devops + glossary views exist
            assert "devops" in result["scan_views"]
            assert "glossary" in result["scan_views"]
            # Other audiences don't have views
            assert "developers" not in result["scan_views"]

    def test_project_model_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert os.path.isfile(result["project_model_path"])


# =============================================================================
# Workspace preparation
# =============================================================================

class TestWorkspace:
    """Directory creation and artifact cleanup."""

    def test_creates_audience_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, result = _run_setup(tmp)
            for aud in ["end-users", "developers", "agents", "devops"]:
                assert os.path.isdir(
                    os.path.join(result["docs_dir_abs"], aud)
                )

    def test_creates_workspace_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, result = _run_setup(tmp)
            assert os.path.isdir(result["tmp_dir"])
            assert os.path.isdir(result["manifests_dir"])
            assert os.path.isdir(result["scan_logs_dir"])

    def test_cleans_stale_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            scan_logs = os.path.join(project_root, ".mg", "docs", "scan-logs")
            os.makedirs(scan_logs, exist_ok=True)
            stale = os.path.join(scan_logs, "terms-old.json")
            _write_json(stale, [])

            _run([
                "--scan-file", scan_path, "--config", config_path,
                "--global-config", config_path, "--scripts-dir", SCRIPTS_DIR,
            ])
            assert not os.path.exists(stale)

    def test_cleans_stale_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            tmp_dir = os.path.join(project_root, ".mg", "docs", "tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            stale = os.path.join(tmp_dir, "write-state-old.json")
            _write_json(stale, {})

            _run([
                "--scan-file", scan_path, "--config", config_path,
                "--global-config", config_path, "--scripts-dir", SCRIPTS_DIR,
            ])
            assert not os.path.exists(stale)

    def test_initial_mode_clears_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            manifests = os.path.join(project_root, ".mg", "docs", "reference-manifests")
            os.makedirs(manifests, exist_ok=True)
            stale = os.path.join(manifests, "old.json")
            _write_json(stale, {})

            _run([
                "--scan-file", scan_path, "--config", config_path,
                "--global-config", config_path, "--scripts-dir", SCRIPTS_DIR,
            ])
            assert not os.path.exists(stale)

    def test_update_mode_preserves_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp, with_docs=True)
            manifests = os.path.join(project_root, ".mg", "docs", "reference-manifests")
            os.makedirs(manifests, exist_ok=True)
            existing = os.path.join(manifests, "existing.json")
            _write_json(existing, {})

            _run([
                "--scan-file", scan_path, "--config", config_path,
                "--global-config", config_path, "--scripts-dir", SCRIPTS_DIR,
            ])
            assert os.path.exists(existing)


# =============================================================================
# Notes
# =============================================================================

class TestNotes:
    """Standing notes loading and grouping."""

    def test_no_inbox_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            for aud in result["audiences"]:
                assert result["notes_by_audience"][aud] == []

    def test_notes_grouped_by_audience(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            inbox = os.path.join(project_root, ".mg", "docs", "notes-inbox.json")
            _write_json(inbox, {"notes": [
                {
                    "id": "note-1",
                    "text": "Fix the intro",
                    "classification": {
                        "audience": "end-users",
                        "document": "USER_GUIDE",
                        "section": "getting-started",
                    },
                },
                {
                    "id": "note-2",
                    "text": "Add rollback steps",
                    "classification": {
                        "audience": "devops",
                        "document": "OPERATIONS",
                        "section": "deployment",
                    },
                },
            ]})

            stdout, _, _ = _run([
                "--scan-file", scan_path, "--config", config_path,
                "--global-config", config_path, "--scripts-dir", SCRIPTS_DIR,
            ])
            result = json.loads(stdout)
            assert len(result["notes_by_audience"]["end-users"]) == 1
            assert len(result["notes_by_audience"]["devops"]) == 1
            assert len(result["notes_by_audience"]["developers"]) == 0


# =============================================================================
# Error cases
# =============================================================================

class TestErrors:
    """Error handling."""

    def test_missing_scan_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "config.json")
            _write_json(config_path, _sample_config())

            _, stderr, rc = _run([
                "--scan-file", os.path.join(tmp, "nonexistent.json"),
                "--config", config_path,
                "--global-config", config_path,
                "--scripts-dir", SCRIPTS_DIR,
            ], check=False)
            assert rc != 0
            assert "scan" in stderr.lower()

    def test_missing_both_configs_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, _ = _make_project(tmp)

            _, stderr, rc = _run([
                "--scan-file", scan_path,
                "--config", os.path.join(tmp, "nope1.json"),
                "--global-config", os.path.join(tmp, "nope2.json"),
                "--scripts-dir", SCRIPTS_DIR,
            ], check=False)
            assert rc != 0
            assert "no config found" in stderr.lower()
