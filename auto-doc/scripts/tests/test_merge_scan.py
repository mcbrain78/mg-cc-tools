"""Tests for merge-scan.py -- merge per-audience scan results into docs-scan.json.

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
    "merge-scan.py",
)


class TestMergeScanBasic:
    """Core merge behavior."""

    def test_merge_two_audience_files(self):
        """Merging 2 per-audience JSON files produces single output with both audiences' data."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            # Create devops scan file
            devops_scan = {
                "source_material_index": {
                    "OPERATIONS/deployment": {
                        "source_files": ["deploy.sh", "docker-compose.yml"],
                        "last_scanned": "2025-01-01T00:00:00+00:00",
                        "stale": False,
                    }
                },
                "staleness_report": [
                    {"document": "OPERATIONS", "section": "deployment",
                     "reason": "config changed", "changed_files": ["config.yml"],
                     "severity": "medium", "suggested_action": "review"}
                ],
                "gap_analysis": {
                    "undocumented_components": ["monitoring"],
                    "missing_for_audience": {"devops": ["scaling-guide"]}
                },
            }
            with open(os.path.join(scan_dir, "scan-devops.json"), "w") as f:
                json.dump(devops_scan, f)

            # Create developers scan file
            dev_scan = {
                "source_material_index": {
                    "ARCHITECTURE/components": {
                        "source_files": ["src/app.py", "src/models.py"],
                        "last_scanned": "2025-01-01T00:00:00+00:00",
                        "stale": False,
                    }
                },
                "staleness_report": [],
                "gap_analysis": {
                    "undocumented_components": ["auth-module"],
                    "missing_for_audience": {"developers": ["api-reference"]}
                },
            }
            with open(os.path.join(scan_dir, "scan-developers.json"), "w") as f:
                json.dump(dev_scan, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test-project",
                 "--root-path", "/tmp/test-project"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"

            with open(output) as f:
                data = json.load(f)

            # Both source material entries present
            assert "OPERATIONS/deployment" in data["source_material_index"]
            assert "ARCHITECTURE/components" in data["source_material_index"]

            # Staleness report from devops present
            assert len(data["staleness_report"]) == 1

            # Gap analysis merged
            assert "monitoring" in data["gap_analysis"]["undocumented_components"]
            assert "auth-module" in data["gap_analysis"]["undocumented_components"]

    def test_empty_scan_dir_produces_valid_output(self):
        """Empty input directory produces valid minimal docs-scan.json."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test-project",
                 "--root-path", "/tmp/test-project"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            assert data["project"] == "test-project"
            assert data["root_path"] == "/tmp/test-project"
            assert data["source_material_index"] == {}
            assert data["staleness_report"] == []


class TestMergeScanDeduplication:
    """Deduplication behavior."""

    def test_source_material_deduplication(self):
        """Duplicate source_material keys keep the one with more source_files."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            # File 1 has key with 1 source file
            scan1 = {
                "source_material_index": {
                    "OVERVIEW/intro": {
                        "source_files": ["README.md"],
                        "last_scanned": "2025-01-01T00:00:00+00:00",
                        "stale": False,
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-file1.json"), "w") as f:
                json.dump(scan1, f)

            # File 2 has same key with 3 source files
            scan2 = {
                "source_material_index": {
                    "OVERVIEW/intro": {
                        "source_files": ["README.md", "CONTRIBUTING.md", "docs/intro.md"],
                        "last_scanned": "2025-01-02T00:00:00+00:00",
                        "stale": False,
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-file2.json"), "w") as f:
                json.dump(scan2, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            # Should keep the version with more source files (3)
            entry = data["source_material_index"]["OVERVIEW/intro"]
            assert len(entry["source_files"]) == 3

    def test_source_material_fusion_preserves_synthesized_from(self):
        """Duplicate keys fuse source_files and preserve synthesized_from from both."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            # File 1: entry with synthesized_from but no source files
            scan1 = {
                "source_material_index": {
                    "OVERVIEW/key-concepts": {
                        "source_files": [],
                        "synthesized_from": ["project_model.components"],
                        "staleness": "unknown",
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-agents.json"), "w") as f:
                json.dump(scan1, f)

            # File 2: same key with source files but no synthesized_from
            scan2 = {
                "source_material_index": {
                    "OVERVIEW/key-concepts": {
                        "source_files": ["README.md", "docs/intro.md"],
                        "staleness": "unknown",
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-devops.json"), "w") as f:
                json.dump(scan2, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            entry = data["source_material_index"]["OVERVIEW/key-concepts"]
            # Fused: source_files from file2, synthesized_from from file1
            assert set(entry["source_files"]) == {"README.md", "docs/intro.md"}
            assert entry["synthesized_from"] == ["project_model.components"]

    def test_source_material_fusion_unions_source_files(self):
        """Duplicate keys union source_files from both entries."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            scan1 = {
                "source_material_index": {
                    "OVERVIEW/intro": {
                        "source_files": ["README.md"],
                        "staleness": "unknown",
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-a.json"), "w") as f:
                json.dump(scan1, f)

            scan2 = {
                "source_material_index": {
                    "OVERVIEW/intro": {
                        "source_files": ["README.md", "CONTRIBUTING.md", "docs/intro.md"],
                        "staleness": "unknown",
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-b.json"), "w") as f:
                json.dump(scan2, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            entry = data["source_material_index"]["OVERVIEW/intro"]
            # Union of source files (3 unique files)
            assert len(entry["source_files"]) == 3
            assert set(entry["source_files"]) == {"README.md", "CONTRIBUTING.md", "docs/intro.md"}

    def test_staleness_deduplication_by_severity(self):
        """Duplicate staleness entries keep highest severity."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            scan1 = {
                "source_material_index": {},
                "staleness_report": [
                    {"document": "OPERATIONS", "section": "deployment",
                     "reason": "minor change", "changed_files": ["a.py"],
                     "severity": "low", "suggested_action": "review"}
                ],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-a.json"), "w") as f:
                json.dump(scan1, f)

            scan2 = {
                "source_material_index": {},
                "staleness_report": [
                    {"document": "OPERATIONS", "section": "deployment",
                     "reason": "major rewrite", "changed_files": ["a.py", "b.py"],
                     "severity": "high", "suggested_action": "rewrite"}
                ],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-b.json"), "w") as f:
                json.dump(scan2, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            # Should have 1 entry (deduplicated) with highest severity
            assert len(data["staleness_report"]) == 1
            assert data["staleness_report"][0]["severity"] == "high"


class TestMergeScanOutputFields:
    """Output format validation."""

    def test_all_required_top_level_fields(self):
        """Output contains all required top-level fields."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test-project",
                 "--root-path", "/tmp/test-project"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            required_fields = [
                "project", "scan_date", "root_path", "mode",
                "project_model", "source_material_index",
                "staleness_report",
                "gap_analysis", "gsd_context",
            ]
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"

    def test_project_name_and_root_path(self):
        """--project-name and --root-path args populate top-level fields."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "my-cool-project",
                 "--root-path", "/home/user/projects/cool"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            assert data["project"] == "my-cool-project"
            assert data["root_path"] == "/home/user/projects/cool"
            assert data["mode"] == "initial"

    def test_scan_date_is_iso_format(self):
        """scan_date is an ISO 8601 timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            assert "T" in data["scan_date"]


class TestMergeScanEdgeCases:
    """Edge cases and error handling."""

    def test_invalid_json_skipped_with_warning(self):
        """Invalid JSON files in scan directory are skipped with warning to stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            # Write invalid JSON
            with open(os.path.join(scan_dir, "scan-bad.json"), "w") as f:
                f.write("{invalid json content")

            # Write valid JSON
            valid_scan = {
                "source_material_index": {
                    "TEST/section": {
                        "source_files": ["test.py"],
                        "last_scanned": "2025-01-01T00:00:00+00:00",
                        "stale": False,
                    }
                },
                "staleness_report": [],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-good.json"), "w") as f:
                json.dump(valid_scan, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            # Warning should be in stderr
            assert "Warning" in result.stderr or "warning" in result.stderr

            with open(output) as f:
                data = json.load(f)

            # Valid file's data should be present
            assert "TEST/section" in data["source_material_index"]

    def test_stderr_summary_message(self):
        """Prints summary to stderr with file count and entry counts."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            scan = {
                "source_material_index": {
                    "A/b": {"source_files": ["a.py"], "last_scanned": "2025-01-01T00:00:00+00:00", "stale": False}
                },
                "staleness_report": [
                    {"document": "A", "section": "b", "reason": "changed",
                     "changed_files": ["a.py"], "severity": "low", "suggested_action": "review"}
                ],
                "gap_analysis": {"undocumented_components": [], "missing_for_audience": {}},
            }
            with open(os.path.join(scan_dir, "scan-test.json"), "w") as f:
                json.dump(scan, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Merged" in result.stderr
            assert "1" in result.stderr  # at least the file count

    def test_mode_argument(self):
        """--mode argument sets the mode field."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_dir)
            output = os.path.join(tmp, "docs-scan.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-dir", scan_dir,
                 "--output", output,
                 "--project-name", "test",
                 "--root-path", "/tmp/test",
                 "--mode", "update"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output) as f:
                data = json.load(f)

            assert data["mode"] == "update"
