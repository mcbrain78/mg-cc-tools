"""Tests for get-section-sources.py -- per-section source file fetcher.

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
    "get-section-sources.py",
)


def _make_scan_data():
    """Build a minimal docs-scan.json for testing."""
    return {
        "source_material_index": {
            "ARCHITECTURE/overview": {
                "source_files": ["src/app.ts", "src/routes/index.ts"],
                "staleness": "fresh",
            },
            "ARCHITECTURE/data-model": {
                "source_files": ["src/db/schema.py"],
                "staleness": "unknown",
            },
            "USER_GUIDE/getting-started": {
                "source_files": [],
                "staleness": "fresh",
                "synthesized_from": ["project_model.components", "project_model.entry_points"],
            },
            "USER_GUIDE/overview": {
                "source_files": ["src/cli/main.py"],
                "staleness": "fresh",
            },
        },
    }


class TestGetSectionSources:
    """Core functionality: returns source_files for a given key."""

    def test_returns_source_files_for_existing_key(self):
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            scan_path = os.path.join(tmp, "docs-scan.json")
            with open(scan_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--scan-file", scan_path,
                 "--key", "ARCHITECTURE/overview"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            output = json.loads(result.stdout)
            assert output["source_files"] == ["src/app.ts", "src/routes/index.ts"]
            assert "synthesized_from" not in output

    def test_returns_synthesized_from_when_present(self):
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            scan_path = os.path.join(tmp, "docs-scan.json")
            with open(scan_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--scan-file", scan_path,
                 "--key", "USER_GUIDE/getting-started"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            output = json.loads(result.stdout)
            assert output["source_files"] == []
            assert output["synthesized_from"] == [
                "project_model.components", "project_model.entry_points"
            ]

    def test_omits_synthesized_from_when_absent(self):
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            scan_path = os.path.join(tmp, "docs-scan.json")
            with open(scan_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--scan-file", scan_path,
                 "--key", "ARCHITECTURE/data-model"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            output = json.loads(result.stdout)
            assert output["source_files"] == ["src/db/schema.py"]
            assert "synthesized_from" not in output


class TestProjectRoot:
    """--project-root derives scan path by convention."""

    def test_project_root_derives_scan_path(self):
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            # Create the conventional scan path
            mg_docs = os.path.join(tmp, ".mg", "docs")
            os.makedirs(mg_docs)
            scan_path = os.path.join(mg_docs, "docs-scan.json")
            with open(scan_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--project-root", tmp,
                 "--key", "ARCHITECTURE/overview"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            output = json.loads(result.stdout)
            assert output["source_files"] == ["src/app.ts", "src/routes/index.ts"]

    def test_project_root_missing_scan_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--project-root", tmp,
                 "--key", "ARCHITECTURE/overview"],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "scan file not found" in result.stderr

    def test_no_root_or_scan_file_exits_2(self):
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--key", "ARCHITECTURE/overview"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2


class TestGetSectionSourcesErrors:
    """Error cases: missing key, missing file."""

    def test_error_on_missing_key(self):
        data = _make_scan_data()
        with tempfile.TemporaryDirectory() as tmp:
            scan_path = os.path.join(tmp, "docs-scan.json")
            with open(scan_path, "w") as f:
                json.dump(data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--scan-file", scan_path,
                 "--key", "NONEXISTENT/section"],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "key not found" in result.stderr

    def test_error_on_missing_scan_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan_path = os.path.join(tmp, "nonexistent.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--scan-file", scan_path,
                 "--key", "ARCHITECTURE/overview"],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "scan file not found" in result.stderr
