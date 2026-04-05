"""Tests for generate-setup.py -- generate pipeline setup.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import importlib.machinery
import importlib.util
import json
import os
import stat
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
                "tmp_dir", "project_model_path", "database_model_path",
                "database_model_summary_path", "db_table_map_path",
                "notes_file", "notes_inbox", "manifests_dir", "scan_logs_dir",
                "mode", "audiences", "audience_filter_active",
                "scan_views", "notes_by_audience",
                "refined_templates", "stale_templates",
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

    def test_cleans_per_run_artifacts(self):
        """project-model.json and db artifacts from prior runs are removed."""
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)
            tmp_dir = os.path.join(project_root, ".mg", "docs", "tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            for name in [
                "project-model.json",
                "database-model.json",
                "database-model-summary.json",
                "db-table-map.json",
            ]:
                _write_json(os.path.join(tmp_dir, name), {"stale": True})

            _run([
                "--scan-file", scan_path, "--config", config_path,
                "--global-config", config_path, "--scripts-dir", SCRIPTS_DIR,
            ])
            # project-model.json should be recreated fresh (not stale)
            pm = _read_json(os.path.join(tmp_dir, "project-model.json"))
            assert "stale" not in pm
            # DB artifacts should be gone (no SQLAlchemy in test fixture)
            assert not os.path.exists(os.path.join(tmp_dir, "database-model-summary.json"))
            assert not os.path.exists(os.path.join(tmp_dir, "db-table-map.json"))

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


# =============================================================================
# Import generate-setup module for direct function testing
# =============================================================================

def _load_module():
    """Load generate-setup.py as a module via importlib (kebab-case filename)."""
    loader = importlib.machinery.SourceFileLoader("generate_setup", SCRIPT_PATH)
    spec = importlib.util.spec_from_loader("generate_setup", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


_mod = _load_module()


def _write_refined_template(path, scan_date="2026-04-01", with_headings=True):
    """Write a mock refined template file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = f"<!-- REFINED: 2026-04-01, scan: {scan_date} -->\n"
    if with_headings:
        content += "\n## Infrastructure Overview\n\nContent here.\n"
        content += "\n### Deployment Topology\n\nMore content.\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# =============================================================================
# Refined template detection (direct function tests)
# =============================================================================

class TestCheckStale:
    """_check_stale helper function tests."""

    def test_stale_when_scan_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-03-30")
            # Scan date 2026-04-02 is newer than template scan date 2026-03-30
            assert _mod._check_stale(path, "2026-04-02") is True

    def test_not_stale_when_dates_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-04-01")
            assert _mod._check_stale(path, "2026-04-01") is False

    def test_not_stale_when_template_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-04-05")
            assert _mod._check_stale(path, "2026-04-01") is False

    def test_stale_when_no_refined_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            with open(path, "w") as f:
                f.write("## Some Heading\n\nNo REFINED comment.\n")
            assert _mod._check_stale(path, "2026-04-01") is True

    def test_stale_when_file_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            with open(path, "w") as f:
                f.write("content")
            os.chmod(path, 0o000)
            try:
                assert _mod._check_stale(path, "2026-04-01") is True
            finally:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    def test_handles_iso8601_scan_date(self):
        """scan_date from docs-scan.json may be ISO 8601 with time component."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-04-01")
            # ISO 8601 with time, same date -> not stale
            assert _mod._check_stale(path, "2026-04-01T14:30:00Z") is False

    def test_handles_iso8601_newer_scan_date(self):
        """ISO 8601 scan date that is newer than template scan date."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-03-31")
            assert _mod._check_stale(path, "2026-04-01T14:30:00Z") is True


class TestDetectRefinedTemplates:
    """detect_refined_templates function tests."""

    def test_returns_path_for_existing_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-04-01")

            audiences = {"devops": {"documents": ["OPERATIONS"]}}
            refined, stale_list = _mod.detect_refined_templates(
                project_root, audiences, "2026-04-01"
            )
            assert refined["devops"]["OPERATIONS"] is not None
            assert refined["devops"]["OPERATIONS"]["path"] == path
            assert refined["devops"]["OPERATIONS"]["stale"] is False

    def test_returns_null_for_missing_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            os.makedirs(project_root)

            audiences = {"end-users": {"documents": ["USER_GUIDE"]}}
            refined, stale_list = _mod.detect_refined_templates(
                project_root, audiences, "2026-04-01"
            )
            assert refined["end-users"]["USER_GUIDE"] is None

    def test_stale_true_when_scan_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-03-30")

            audiences = {"devops": {"documents": ["OPERATIONS"]}}
            refined, stale_list = _mod.detect_refined_templates(
                project_root, audiences, "2026-04-01"
            )
            assert refined["devops"]["OPERATIONS"]["stale"] is True

    def test_no_headings_treated_as_absent(self):
        """Template with no ## headings should return null."""
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-04-01", with_headings=False)

            audiences = {"devops": {"documents": ["OPERATIONS"]}}
            refined, stale_list = _mod.detect_refined_templates(
                project_root, audiences, "2026-04-01"
            )
            assert refined["devops"]["OPERATIONS"] is None

    def test_stale_templates_list(self):
        """stale_templates list contains audience/document strings."""
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-03-01")

            audiences = {"devops": {"documents": ["OPERATIONS"]}}
            refined, stale_list = _mod.detect_refined_templates(
                project_root, audiences, "2026-04-01"
            )
            assert "devops/OPERATIONS" in stale_list

    def test_stale_list_empty_when_not_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(path, scan_date="2026-04-01")

            audiences = {"devops": {"documents": ["OPERATIONS"]}}
            refined, stale_list = _mod.detect_refined_templates(
                project_root, audiences, "2026-04-01"
            )
            assert stale_list == []


# =============================================================================
# CLI integration: refined_templates in full output
# =============================================================================

class TestRefinedTemplatesCLI:
    """Full CLI run includes refined_templates and stale_templates keys."""

    def test_output_includes_refined_templates_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert "refined_templates" in result
            assert "stale_templates" in result

    def test_cli_detects_existing_refined_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            # Add scan_date to scan file
            scan_data = _read_json(scan_path)
            scan_data["scan_date"] = "2026-04-01T14:30:00Z"
            _write_json(scan_path, scan_data)

            # Create a refined template for devops/OPERATIONS
            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            tpl_path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(tpl_path, scan_date="2026-04-01")

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--scripts-dir", SCRIPTS_DIR,
            ])
            result = json.loads(stdout)

            assert result["refined_templates"]["devops"]["OPERATIONS"] is not None
            assert result["refined_templates"]["devops"]["OPERATIONS"]["stale"] is False
            assert result["refined_templates"]["end-users"]["USER_GUIDE"] is None

    def test_cli_stale_template_in_stale_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root, scan_path, config_path = _make_project(tmp)

            scan_data = _read_json(scan_path)
            scan_data["scan_date"] = "2026-04-02T10:00:00Z"
            _write_json(scan_path, scan_data)

            templates_base = os.path.join(
                project_root, ".mg", "docs", "templates", "devops"
            )
            tpl_path = os.path.join(templates_base, "OPERATIONS.template.md")
            _write_refined_template(tpl_path, scan_date="2026-03-15")

            stdout, _, _ = _run([
                "--scan-file", scan_path,
                "--config", config_path,
                "--global-config", config_path,
                "--scripts-dir", SCRIPTS_DIR,
            ])
            result = json.loads(stdout)

            assert "devops/OPERATIONS" in result["stale_templates"]


# =============================================================================
# Database model extraction
# =============================================================================

class TestDatabaseModelPath:
    """database_model_path in output."""

    def test_null_when_no_database(self):
        """No database in project model -> database_model_path is null."""
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert result["database_model_path"] is None

    def test_present_in_output_keys(self):
        """database_model_path is always present in output."""
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _run_setup(tmp)
            assert "database_model_path" in result
