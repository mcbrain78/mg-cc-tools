"""Tests for extract-verify-context.py -- extract verify context from scan data.

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
    "extract-verify-context.py",
)


def _full_scan_data():
    """Return a realistic scan data dict with many fields."""
    return {
        "root_path": "/home/user/project",
        "scan_timestamp": "2026-03-25T10:00:00Z",
        "source_material_index": {
            "src/main.py": {
                "type": "module",
                "symbols": ["main", "setup", "run"],
                "description": "Main entry point",
            },
            "src/utils.py": {
                "type": "module",
                "symbols": ["helper", "format_output"],
                "description": "Utility functions",
            },
        },
        "gap_analysis": {
            "missing_for_audience": {
                "devops": ["deployment", "monitoring"],
                "end-user": ["getting-started"],
            }
        },
        "project_model": {"name": "test-project", "version": "1.0"},
        "audiences": ["developer", "devops", "end-user"],
        "large_data_blob": "x" * 10000,
    }


class TestExtractVerifyContext:
    """Core extraction behavior."""

    def test_extracts_correct_fields(self):
        """Output contains root_path, source_material_index, gap_analysis."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            with open(scan_file, "w") as f:
                json.dump(_full_scan_data(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                context = json.load(f)

            assert context["root_path"] == "/home/user/project"
            assert "src/main.py" in context["source_material_index"]
            assert "src/utils.py" in context["source_material_index"]
            assert "missing_for_audience" in context["gap_analysis"]
            # Only 3 keys in output
            assert set(context.keys()) == {"root_path", "source_material_index", "gap_analysis"}

    def test_output_smaller_than_input(self):
        """Output file size is smaller than input file size."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            with open(scan_file, "w") as f:
                json.dump(_full_scan_data(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            input_size = os.path.getsize(scan_file)
            output_size = os.path.getsize(output_file)
            assert output_size < input_size

    def test_missing_optional_fields(self):
        """Scan data without gap_analysis produces empty dict for that field."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            scan_data = {"root_path": "/home/user/project"}
            with open(scan_file, "w") as f:
                json.dump(scan_data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                context = json.load(f)

            assert context["root_path"] == "/home/user/project"
            assert context["source_material_index"] == {}
            assert context["gap_analysis"] == {}

    def test_missing_scan_file_exits_nonzero(self):
        """Missing scan file exits non-zero with error message."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "nonexistent.json")
            output_file = os.path.join(tmp, "context.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
            assert "not found" in result.stderr
