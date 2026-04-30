"""Tests for split-scan-by-audience.py -- per-audience and glossary scan view splitter.

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
    "split-scan-by-audience.py",
)


def _make_scan_data():
    """Build a realistic docs-scan.json for testing."""
    return {
        "project": "test-project",
        "scan_date": "2026-03-23T14:00:00Z",
        "root_path": "/home/user/test-project",
        "mode": "initial",
        "last_generated": None,
        "project_model": {
            "tech_stack": ["python", "typescript"],
            "entry_points": [
                {"path": "main.py", "type": "cli", "description": "Entry point"}
            ],
            "components": [
                {
                    "name": "core",
                    "path": "src/core.py",
                    "purpose": "Core logic",
                    "public_api": ["run"],
                    "dependencies": [],
                    "database_tables": [],
                }
            ],
            "infrastructure": {
                "deployment": "pip install",
                "ci": "github-actions",
                "config_files": ["pyproject.toml"],
            },
            "database": {
                "orm_framework": "SQLAlchemy 2.0",
                "migration_tool": "Alembic",
                "schemas": {
                    "public": {
                        "tables": ["users", "sessions"],
                        "migration_chain": "alembic_main",
                    }
                },
            },
        },
        "gsd_context": {
            "milestone": "v1.0",
            "completed_phases": ["01-foundation"],
            "deviations": [],
            "new_requirements_completed": ["AUTH-01"],
        },
        "source_material_index": {
            "ARCHITECTURE/overview": {
                "source_files": ["src/app.ts", "src/routes/index.ts"],
                "staleness": "fresh",
            },
            "ARCHITECTURE/data-model": {
                "source_files": ["src/db/schema.py"],
                "staleness": "unknown",
            },
            "DEVELOPER_GUIDE/setup": {
                "source_files": ["scripts/setup.sh"],
                "staleness": "fresh",
            },
            "USER_GUIDE/getting-started": {
                "source_files": ["src/cli/main.py"],
                "staleness": "stale",
            },
            "USER_GUIDE/overview": {
                "source_files": [],
                "staleness": "fresh",
                "synthesized_from": ["project_model.components"],
            },
            "SYSTEM_MAP/components": {
                "source_files": ["src/core.py", "src/utils/helpers.py"],
                "staleness": "fresh",
            },
            "OPERATIONS/deployment": {
                "source_files": ["/home/user/test-project/deploy/run.sh"],
                "staleness": "unknown",
            },
        },
        "gap_analysis": {
            "undocumented_components": ["src/utils/helpers.py"],
            "missing_for_audience": {
                "end-users": ["installation"],
                "developers": ["api-reference"],
                "agents": [],
                "devops": ["monitoring"],
            },
        },
        "staleness_report": [
            {
                "document": "USER_GUIDE",
                "section": "getting-started",
                "reason": "Source changed",
                "changed_files": ["src/cli/main.py"],
                "severity": "high",
                "suggested_action": "Regenerate",
            }
        ],
    }


def _run_script(args, scan_data=None, tmp_dir=None):
    """Run split-scan-by-audience.py with given args.

    If scan_data is provided, writes it to a temp input file.
    Returns subprocess.CompletedProcess.
    """
    if tmp_dir is None:
        raise ValueError("tmp_dir required")

    if scan_data is not None:
        input_path = os.path.join(tmp_dir, "docs-scan.json")
        with open(input_path, "w") as f:
            json.dump(scan_data, f)
        # Replace --input placeholder with actual path
        args = [input_path if a == "__INPUT__" else a for a in args]

    return subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True,
        text=True,
    )


class TestAudienceModeFiltering:
    """Audience mode: filters source_material_index by --documents list."""

    def test_filters_source_material_index_by_documents(self):
        """Test 1: Only keys whose document prefix matches --documents are kept."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"

            with open(output_path) as f:
                view = json.load(f)

            smi = view["source_material_index"]
            assert "ARCHITECTURE/overview" in smi
            assert "ARCHITECTURE/data-model" in smi
            assert "DEVELOPER_GUIDE/setup" in smi
            # These should be filtered out
            assert "USER_GUIDE/getting-started" not in smi
            assert "SYSTEM_MAP/components" not in smi
            assert "OPERATIONS/deployment" not in smi

    def test_strips_source_files_from_entries(self):
        """Test 1b: source_files are stripped from audience view entries."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            for key, entry in view["source_material_index"].items():
                assert "source_files" not in entry, f"{key} should not have source_files"

    def test_preserves_staleness_in_entries(self):
        """Test 1c: staleness is preserved in audience view entries."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            assert view["source_material_index"]["ARCHITECTURE/overview"]["staleness"] == "fresh"
            assert view["source_material_index"]["ARCHITECTURE/data-model"]["staleness"] == "unknown"

    def test_does_not_include_project_model(self):
        """Test 2: project_model is NOT included in view files (extracted separately)."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            assert "project_model" not in view

    def test_filters_gap_analysis_missing_for_audience(self):
        """Test 3: gap_analysis.missing_for_audience filtered to target audience only;
        undocumented_components preserved verbatim."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            gap = view["gap_analysis"]
            assert gap["undocumented_components"] == ["src/utils/helpers.py"]
            assert "developers" in gap["missing_for_audience"]
            assert gap["missing_for_audience"]["developers"] == ["api-reference"]
            # Other audiences should be filtered out
            assert "end-users" not in gap["missing_for_audience"]
            assert "agents" not in gap["missing_for_audience"]
            assert "devops" not in gap["missing_for_audience"]

    def test_omits_excluded_keys(self):
        """Test 4: staleness_report, scan_date, project, root_path, mode,
        last_generated are all omitted from output."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            for excluded in [
                "staleness_report", "scan_date",
                "project", "root_path", "mode", "last_generated",
            ]:
                assert excluded not in view, f"{excluded} should be omitted"

    def test_missing_audience_arg_exits_nonzero(self):
        """Test 5a: Exits non-zero if --audience missing in audience mode."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--documents", "ARCHITECTURE",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_documents_arg_exits_nonzero(self):
        """Test 5b: Exits non-zero if --documents missing in audience mode."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_output_has_exactly_three_top_level_keys(self):
        """Test 6: Output has exactly gsd_context,
        source_material_index, and gap_analysis at top level."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            expected_keys = {"gsd_context", "source_material_index", "gap_analysis"}
            assert set(view.keys()) == expected_keys


class TestGlossaryMode:
    """Glossary mode: preserves all keys, strips source_files."""

    def test_preserves_all_source_material_index_keys(self):
        """Test 7: All source_material_index keys are preserved (no document filtering)."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"

            with open(output_path) as f:
                view = json.load(f)

            smi = view["source_material_index"]
            # All 7 keys from the fixture should be present
            assert len(smi) == 7
            assert "ARCHITECTURE/overview" in smi
            assert "USER_GUIDE/getting-started" in smi
            assert "SYSTEM_MAP/components" in smi
            assert "OPERATIONS/deployment" in smi

    def test_strips_source_files_from_entries(self):
        """Test 8: source_files are stripped from glossary view entries."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            for key, entry in view["source_material_index"].items():
                assert "source_files" not in entry, f"{key} should not have source_files"

    def test_preserves_staleness_in_entries(self):
        """Test 8b: staleness is preserved in glossary view entries."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            assert view["source_material_index"]["ARCHITECTURE/overview"]["staleness"] == "fresh"

    def test_preserves_synthesized_from_when_present(self):
        """Test 8c: synthesized_from is preserved in glossary view entries."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            entry = view["source_material_index"]["USER_GUIDE/overview"]
            assert entry["synthesized_from"] == ["project_model.components"]
            # Entry without synthesized_from should not have it
            assert "synthesized_from" not in view["source_material_index"]["ARCHITECTURE/overview"]

    def test_does_not_include_project_model_copies_gsd_context(self):
        """Test 9: project_model is NOT in view; gsd_context is copied unchanged."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            assert "project_model" not in view
            assert view["gsd_context"] == data["gsd_context"]

    def test_includes_full_gap_analysis(self):
        """Test 10: Full gap_analysis (all audiences) is included."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            assert view["gap_analysis"] == data["gap_analysis"]

    def test_output_has_exactly_three_top_level_keys(self):
        """Test 11: Output has exactly 3 top-level keys."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            expected_keys = {"gsd_context", "source_material_index", "gap_analysis"}
            assert set(view.keys()) == expected_keys


class TestEdgeCases:
    """Edge cases: empty data, missing fields, mixed paths."""

    def test_empty_source_material_index(self):
        """Test 12: Empty source_material_index produces empty dict, not error."""
        data = _make_scan_data()
        data["source_material_index"] = {}
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                view = json.load(f)

            assert view["source_material_index"] == {}

    def test_missing_gap_analysis_produces_empty_dict(self):
        """Test 13: Missing gap_analysis in input produces empty dict in output."""
        data = _make_scan_data()
        del data["gap_analysis"]
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                view = json.load(f)

            assert view["gap_analysis"] == {}

    def test_source_files_stripped_regardless_of_path_format(self):
        """Test 14: source_files are stripped even with mixed path formats."""
        data = _make_scan_data()
        data["source_material_index"] = {
            "ARCHITECTURE/mixed-paths": {
                "source_files": [
                    "src/normal/path.py",
                    "/absolute/path/to/file.ts",
                    "deeply/nested/dir/module.js",
                ],
                "staleness": "fresh",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-glossary.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "glossary",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                view = json.load(f)

            entry = view["source_material_index"]["ARCHITECTURE/mixed-paths"]
            assert "source_files" not in entry
            assert entry["staleness"] == "fresh"


class TestProjectModelExtraction:
    """--project-model-output: standalone slimmed project model file."""

    def test_writes_project_model_json(self):
        """Writes project-model.json with correct content."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE,DEVELOPER_GUIDE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert os.path.exists(pm_path)

            with open(pm_path) as f:
                pm = json.load(f)

            # Top-level keys preserved
            assert "tech_stack" in pm
            assert "entry_points" in pm
            assert "components" in pm
            assert "infrastructure" in pm

    def test_strips_public_api_preserves_database_tables(self):
        """Strips public_api but preserves database_tables for db-table-map."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(pm_path) as f:
                pm = json.load(f)

            for comp in pm["components"]:
                assert "public_api" not in comp, f"{comp['name']} should not have public_api"
                assert "database_tables" in comp, f"{comp['name']} should preserve database_tables"

    def test_preserves_component_core_fields(self):
        """Preserves name, path, purpose, dependencies in components."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(pm_path) as f:
                pm = json.load(f)

            comp = pm["components"][0]
            assert comp["name"] == "core"
            assert comp["path"] == "src/core.py"
            assert comp["purpose"] == "Core logic"
            assert comp["dependencies"] == []

    def test_skips_write_if_file_exists(self):
        """Does not overwrite existing project-model.json."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            # Pre-create a sentinel file
            sentinel = {"sentinel": True}
            with open(pm_path, "w") as f:
                json.dump(sentinel, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(pm_path) as f:
                pm = json.load(f)

            # Sentinel data should be unchanged
            assert pm == sentinel

    def test_no_file_written_without_flag(self):
        """Without --project-model-output, no project-model.json is written."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                ],
                capture_output=True, text=True,
            )

            assert not os.path.exists(pm_path)

    def test_view_file_has_no_project_model_with_flag(self):
        """View file still has no project_model even when --project-model-output is used."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(output_path) as f:
                view = json.load(f)

            assert "project_model" not in view
            expected_keys = {"gsd_context", "source_material_index", "gap_analysis"}
            assert set(view.keys()) == expected_keys

    def test_strips_database_schemas_preserves_metadata(self):
        """database.schemas is stripped; orm_framework and migration_tool preserved."""
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(pm_path) as f:
                pm = json.load(f)

            assert "database" in pm
            assert pm["database"]["orm_framework"] == "SQLAlchemy 2.0"
            assert pm["database"]["migration_tool"] == "Alembic"
            # schemas stripped -- now in database-model.json
            assert "schemas" not in pm["database"]

    def test_strips_database_design_notes(self):
        """database.design_notes is stripped from slimmed project model."""
        data = _make_scan_data()
        data["project_model"]["database"]["design_notes"] = "Some LLM notes"
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(pm_path) as f:
                pm = json.load(f)

            assert "design_notes" not in pm["database"]

    def test_null_database_unaffected(self):
        """database: null is preserved as-is by slim_project_model."""
        data = _make_scan_data()
        data["project_model"]["database"] = None
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "docs-scan.json")
            output_path = os.path.join(tmp, "scan-view-developers.json")
            pm_path = os.path.join(tmp, "project-model.json")
            with open(input_path, "w") as f:
                json.dump(data, f)

            subprocess.run(
                [
                    sys.executable, SCRIPT_PATH,
                    "--input", input_path,
                    "--output", output_path,
                    "--mode", "audience",
                    "--audience", "developers",
                    "--documents", "ARCHITECTURE",
                    "--project-model-output", pm_path,
                ],
                capture_output=True, text=True,
            )

            with open(pm_path) as f:
                pm = json.load(f)

            assert pm["database"] is None
